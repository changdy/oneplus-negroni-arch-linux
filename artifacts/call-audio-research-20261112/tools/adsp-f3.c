// SPDX-License-Identifier: GPL-2.0
// Derived from royka1/diting-ubuntu tools/diag/adsp_diag.c,
// commit c68ff47db94792fb5fd608e98d1ae489c2e592b1.
// Local variant: F3 only, no binary audio/event recording, bounded lifetime.
// Original source is kept alongside this file as adsp_diag.c.
#include <ctype.h>
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/file.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>
#include <linux/qrtr.h>
#ifndef QRTR_PORT_CTRL
#define QRTR_PORT_CTRL 0xfffffffeu
#endif
#define DIAG_SVC_ID 0x1001
#define DIAG_CTRL_MSG_FEATURE 8
#define DIAG_CTRL_MSG_DIAGID 33
#define DIAG_CTRL_MSG_DIAGMODE 3
#define MAX_PKT 0x4400
static volatile sig_atomic_t stop;
static unsigned long f3_count, ignored_count;
static void on_signal(int sig) { (void)sig; stop = 1; }
static double mono_sec(void) {
    struct timespec ts; clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec + ts.tv_nsec / 1e9;
}
static void dlog(const char *fmt, ...) {
    va_list ap; fprintf(stderr, "[%9.3f] ", mono_sec());
    va_start(ap, fmt); vfprintf(stderr, fmt, ap); va_end(ap); fflush(stderr);
}
static int serve(uint32_t service, uint32_t instance, const char *what)
{
	struct sockaddr_qrtr sq;
	struct qrtr_ctrl_pkt pkt;
	socklen_t sl = sizeof(sq);
	int fd;

	fd = socket(AF_QIPCRTR, SOCK_DGRAM, 0);
	if (fd < 0) {
		dlog("%s: socket: %s\n", what, strerror(errno));
		return -1;
	}

	memset(&sq, 0, sizeof(sq));
	sq.sq_family = AF_QIPCRTR;
	sq.sq_node = 1;
	sq.sq_port = 0;
	if (bind(fd, (struct sockaddr *)&sq, sizeof(sq)) < 0) {
		dlog("%s: bind: %s\n", what, strerror(errno));
		close(fd);
		return -1;
	}
	if (getsockname(fd, (struct sockaddr *)&sq, &sl) < 0) {
		dlog("%s: getsockname: %s\n", what, strerror(errno));
		close(fd);
		return -1;
	}

	memset(&pkt, 0, sizeof(pkt));
	pkt.cmd = QRTR_TYPE_NEW_SERVER;
	pkt.server.service = service;
	pkt.server.instance = instance;
	pkt.server.node = sq.sq_node;
	pkt.server.port = sq.sq_port;

	sq.sq_port = QRTR_PORT_CTRL;
	if (sendto(fd, &pkt, sizeof(pkt), 0, (struct sockaddr *)&sq,
		   sizeof(sq)) < 0) {
		dlog("%s: NEW_SERVER(%u/%u): %s\n", what, service, instance,
		     strerror(errno));
		close(fd);
		return -1;
	}

	dlog("%s: serving %#x/%u\n", what, service, instance);
	return fd;
}

static void unpublish(int fd, uint32_t service, uint32_t instance)
{
	struct sockaddr_qrtr sq = {0};
	struct qrtr_ctrl_pkt pkt;
	socklen_t sl = sizeof(sq);

	if (fd < 0 || getsockname(fd, (struct sockaddr *)&sq, &sl) < 0)
		return;

	memset(&pkt, 0, sizeof(pkt));
	pkt.cmd = QRTR_TYPE_DEL_SERVER;
	pkt.server.service = service;
	pkt.server.instance = instance;
	pkt.server.node = sq.sq_node;
	pkt.server.port = sq.sq_port;

	sq.sq_port = QRTR_PORT_CTRL;
	sendto(fd, &pkt, sizeof(pkt), 0, (struct sockaddr *)&sq, sizeof(sq));
}

/*
 * Ask the router to tell us about every server of @service. The ADSP's CMD
 * instance is one of them, and its address is the only way to send it anything.
 */
static int start_lookup(uint32_t service)
{
	struct sockaddr_qrtr sq;
	struct qrtr_ctrl_pkt pkt;
	int fd;

	fd = socket(AF_QIPCRTR, SOCK_DGRAM, 0);
	if (fd < 0)
		return -1;

	memset(&sq, 0, sizeof(sq));
	sq.sq_family = AF_QIPCRTR;
	sq.sq_node = 1;
	sq.sq_port = 0;
	if (bind(fd, (struct sockaddr *)&sq, sizeof(sq)) < 0) {
		close(fd);
		return -1;
	}

	memset(&pkt, 0, sizeof(pkt));
	pkt.cmd = QRTR_TYPE_NEW_LOOKUP;
	pkt.server.service = service;
	pkt.server.instance = 0;

	sq.sq_port = QRTR_PORT_CTRL;
	if (sendto(fd, &pkt, sizeof(pkt), 0, (struct sockaddr *)&sq,
		   sizeof(sq)) < 0) {
		dlog("NEW_LOOKUP(%#x): %s\n", service, strerror(errno));
		close(fd);
		return -1;
	}

	return fd;
}


static void reply_feature(int fd, const struct sockaddr_qrtr *to,
			  const uint8_t *mask, uint32_t masklen)
{
	uint8_t pkt[64];
	uint32_t v;
	size_t off = 0;

	if (masklen > sizeof(pkt) - 12)
		return;

	v = DIAG_CTRL_MSG_FEATURE;	memcpy(pkt + off, &v, 4); off += 4;
	v = 4 + masklen;		memcpy(pkt + off, &v, 4); off += 4;
	v = masklen;			memcpy(pkt + off, &v, 4); off += 4;
	memcpy(pkt + off, mask, masklen);
	/*
	 * Do not agree to multi-SIM masks (F_DIAG_MULTI_SIM_SUPPORT, bit 20):
	 * the modem then expects the longer diag_ctrl_msg_mask_sub layout.
	 */
	if (masklen > 2)
		pkt[off + 2] &= ~0x10;
	off += masklen;

	if (sendto(fd, pkt, off, MSG_DONTWAIT, (const struct sockaddr *)to,
		   sizeof(*to)) < 0)
		dlog("feature reply: %s\n", strerror(errno));
	else
		dlog("answered FEATURE (%u mask bytes)\n", masklen);
}


static void reply_diagid(int fd, const struct sockaddr_qrtr *to,
			 uint32_t diag_id, const char *name)
{
	uint8_t pkt[64];
	size_t nlen = strlen(name) + 1;
	uint32_t v;
	size_t off = 0;

	if (nlen > sizeof(pkt) - 16)
		return;

	v = DIAG_CTRL_MSG_DIAGID;	memcpy(pkt + off, &v, 4); off += 4;
	v = 4 + 4 + nlen;		memcpy(pkt + off, &v, 4); off += 4;
	v = 1;				memcpy(pkt + off, &v, 4); off += 4;
	v = diag_id;			memcpy(pkt + off, &v, 4); off += 4;
	memcpy(pkt + off, name, nlen); off += nlen;

	if (sendto(fd, pkt, off, MSG_DONTWAIT, (const struct sockaddr *)to,
		   sizeof(*to)) < 0)
		dlog("diagid reply: %s\n", strerror(errno));
	else
		dlog("assigned diag_id %u to \"%s\"\n", diag_id, name);
}

/*
 * Pull the process name out of a DIAGID record. Version 2 carries a
 * variable-length feature mask between the id and the name, so the name is not
 * at a fixed offset.
 */
static const char *diagid_name(const uint8_t *buf, size_t n)
{
	uint32_t version, feature_len;
	size_t off;

	if (n < 16)
		return NULL;
	memcpy(&version, buf + 8, 4);

	if (version == 2) {
		if (n < 20)
			return NULL;
		memcpy(&feature_len, buf + 16, 4);
		off = 20 + feature_len;
	} else {
		off = 16;
	}
	if (off >= n)
		return NULL;

	/* Must be NUL-terminated inside the packet to be safe to print. */
	if (!memchr(buf + off, 0, n - off))
		return NULL;

	return (const char *)buf + off;
}


static void send_realtime(int fd, const struct sockaddr_qrtr *to,
			  uint8_t diag_id)
{
	struct {
		uint32_t ctrl_pkt_id;
		uint32_t ctrl_pkt_data_len;
		uint32_t version;
		uint32_t sleep_vote;
		uint32_t real_time;
		uint32_t use_nrt_values;
		uint32_t commit_threshold;
		uint32_t sleep_threshold;
		uint32_t sleep_time;
		uint32_t drain_timer_val;
		uint32_t event_stale_timer_val;
		uint8_t diag_id;
	} __attribute__((packed)) m = {
		.ctrl_pkt_id = DIAG_CTRL_MSG_DIAGMODE,
		.ctrl_pkt_data_len = sizeof(m) - 8,
		.version = 2,
		.sleep_vote = 1,
		.real_time = 1,
		.diag_id = diag_id,
	};

	if (sendto(fd, &m, sizeof(m), MSG_DONTWAIT, (const struct sockaddr *)to,
		   sizeof(*to)) < 0)
		dlog("diagmode: %s\n", strerror(errno));
	else
		dlog("REALTIME on for diag_id %u\n", diag_id);
}



static void print_ext_msg(const uint8_t *p, size_t n)
{
	uint32_t args[16], mask;
	uint16_t line, ssid;
	const char *fmt, *file;
	size_t off, i, nargs;
	uint64_t ts;
	int ai = 0;

	if (n < 20)
		return;
	nargs = p[2];
	if (nargs > 16 || 20 + nargs * 4 >= n)
		return;

	memcpy(&ts, p + 4, 8);
	memcpy(&line, p + 12, 2);
	memcpy(&ssid, p + 14, 2);
	memcpy(&mask, p + 16, 4);
	for (i = 0; i < nargs; i++)
		memcpy(&args[i], p + 20 + i * 4, 4);

	off = 20 + nargs * 4;
	fmt = (const char *)p + off;
	if (!memchr(p + off, 0, n - off))
		return;
	off += strlen(fmt) + 1;
	file = (off < n && memchr(p + off, 0, n - off)) ? (const char *)p + off
						       : "?";

	printf("%-28s:%-5u ssid=%-5u ", file, line, ssid);

	for (i = 0; fmt[i]; i++) {
		char spec[24];
		size_t j = 0;

		if (fmt[i] != '%') {
			putchar(fmt[i]);
			continue;
		}
		if (fmt[i + 1] == '%') {
			putchar('%');
			i++;
			continue;
		}

		spec[j++] = '%';
		i++;
		/* flags, width, precision */
		while (fmt[i] && (strchr("-+ #0", fmt[i]) || isdigit(fmt[i]) ||
				  fmt[i] == '.') && j < sizeof(spec) - 4)
			spec[j++] = fmt[i++];
		/* length modifiers are dropped: every argument is 32-bit */
		while (fmt[i] == 'l' || fmt[i] == 'h' || fmt[i] == 'z')
			i++;

		if (!fmt[i])
			break;

		switch (fmt[i]) {
		case 'd': case 'i':
			spec[j++] = 'd'; spec[j] = 0;
			printf(spec, ai < (int)nargs ? (int)args[ai++] : 0);
			break;
		case 'u': case 'x': case 'X': case 'o': case 'p':
			spec[j++] = (fmt[i] == 'p') ? 'x' : fmt[i];
			spec[j] = 0;
			printf(spec, ai < (int)nargs ? args[ai++] : 0);
			break;
		case 'c':
			spec[j++] = 'c'; spec[j] = 0;
			printf(spec, ai < (int)nargs ? (int)args[ai++] : '?');
			break;
		case 's':
			fputs("<str>", stdout);
			if (ai < (int)nargs) ai++;
			break;
		default:
			putchar(fmt[i]);
			break;
		}
	}
	putchar('\n');
}



/* All mask statuses are from Qualcomm diag_masks.h:
 * INVALID=0, ALL_DISABLED=1, ALL_ENABLED=2, VALID=3.
 */
struct diag_peer {
    struct sockaddr_qrtr addr;
    int valid;
    uint16_t ranges[256][2];
    uint32_t count;
};
static void binary_off(int fd, const struct sockaddr_qrtr *to) {
    struct {
        uint32_t id, len;
        uint8_t stream, status, equip;
        uint32_t count, size;
    } __attribute__((packed)) logs = {9, 11, 1, 1, 0, 0, 0};
    struct {
        uint32_t id, len;
        uint8_t stream, status, enabled;
        uint32_t size;
    } __attribute__((packed)) events = {10, 7, 1, 1, 0, 0};
    if (sendto(fd, &logs, sizeof(logs), MSG_DONTWAIT,
               (const struct sockaddr *)to, sizeof(*to)) < 0)
        dlog("disable binary logs: %s\n", strerror(errno));
    if (sendto(fd, &events, sizeof(events), MSG_DONTWAIT,
               (const struct sockaddr *)to, sizeof(*to)) < 0)
        dlog("disable events: %s\n", strerror(errno));
}
static void f3_masks(int fd, const struct diag_peer *p, int enable) {
    for (uint32_t i = 0; i < p->count; i++) {
        struct {
            uint32_t id, len;
            uint8_t stream, status, mode;
            uint16_t first, last;
            uint32_t count, mask;
        } __attribute__((packed)) m = {
            11, enable ? 15 : 11, 1, enable ? 2 : 1, 0,
            p->ranges[i][0], p->ranges[i][1], enable ? 1 : 0,
            enable ? 0xffffffffu : 0
        };
        size_t len = enable ? sizeof(m) : sizeof(m) - 4;
        if (sendto(fd, &m, len, MSG_DONTWAIT,
                   (const struct sockaddr *)&p->addr, sizeof(p->addr)) < 0)
            dlog("F3 mask %u-%u: %s\n", m.first, m.last, strerror(errno));
    }
}
static void streaming(int fd, const struct sockaddr_qrtr *to) {
    struct {
        uint32_t id, len, version;
        uint8_t stream, mode;
    } __attribute__((packed)) m = {17, 6, 1, 1, 0};
    if (sendto(fd, &m, sizeof(m), MSG_DONTWAIT,
               (const struct sockaddr *)to, sizeof(*to)) < 0)
        dlog("streaming mode: %s\n", strerror(errno));
}
static void control(int fd, struct diag_peer *p,
                    const struct sockaddr_qrtr *from, const uint8_t *buf,
                    size_t n, uint32_t *diag_id) {
    if (p->valid && (p->addr.sq_node != from->sq_node ||
                    p->addr.sq_port != from->sq_port)) {
        dlog("ignoring different peripheral %u:%u\n",
             from->sq_node, from->sq_port);
        return;
    }
    if (!p->valid) {
        p->addr = *from; p->valid = 1;
        dlog("ADSP control peer %u:%u\n", from->sq_node, from->sq_port);
    }
    size_t o = 0;
    while (o + 8 <= n) {
        uint32_t id, size;
        memcpy(&id, buf + o, 4); memcpy(&size, buf + o + 4, 4);
        if (size > n - o - 8) { dlog("truncated control %u\n", id); break; }
        const uint8_t *b = buf + o;
        size_t len = 8 + size;
        if (id == 8 && len >= 12) {
            uint32_t ml; memcpy(&ml, b + 8, 4);
            if (ml <= len - 12) {
                reply_feature(fd, from, b + 12, ml);
                binary_off(fd, from); streaming(fd, from);
            }
        } else if (id == 33) {
            const char *name = diagid_name(b, len);
            if (name && *diag_id < 255) {
                reply_diagid(fd, from, ++*diag_id, name);
                send_realtime(fd, from, *diag_id);
                binary_off(fd, from); streaming(fd, from);
                if (p->count) f3_masks(fd, p, 1);
            }
        } else if (id == 24 && len >= 16) {
            uint32_t count; memcpy(&count, b + 12, 4);
            if (count <= 256 && count <= (len - 16) / 4) {
                p->count = count;
                memcpy(p->ranges, b + 16, count * 4);
                binary_off(fd, from);
                f3_masks(fd, p, 1);
                dlog("enabled F3 for %u SSID ranges; binary logs/events disabled\n", count);
            }
        }
        o += len;
    }
}
/* Only F3 forms are printed; all binary logs/events/unknowns are discarded.
 * Never print a raw packet or accept a log-dump option. */
static void decode_data(const uint8_t *buf, size_t n) {
    size_t o = 4;
    if (n < 8) return;
    while (o + 4 <= n) {
        if (buf[o] != 0x7e) { o++; continue; }
        uint16_t len; memcpy(&len, buf + o + 2, 2);
        if (!len || len > n - o - 4) break;
        const uint8_t *p = buf + o + 4;
        if (p[0] == 0x79) {
            f3_count++; print_ext_msg(p, len);
        } else if (p[0] == 0x92 && len >= 24) {
            uint16_t line, ssid; uint32_t hash, arg;
            memcpy(&line,p+12,2); memcpy(&ssid,p+14,2); memcpy(&hash,p+20,4);
            printf("Q %u %u %u",hash,ssid,line);
            for (unsigned int i=0; i<p[2] && 28+4*i<=len; i++) {
                memcpy(&arg,p+24+4*i,4); printf(" 0x%x",arg);
            }
            putchar('\n'); f3_count++;
        } else {
            ignored_count++;
        }
        o += 4 + len;
        if (o < n && buf[o] == 0x7e) o++;
    }
    fflush(stdout);
}
static int selftest(void) {
    /* A DIAG binary log frame must never reach stdout. */
    uint8_t b[] = {0,0,0,0, 0x7e,1,8,0, 0x10,1,2,3,4,5,6,7, 0x7e};
    decode_data(b,sizeof(b));
    if (ignored_count != 1 || f3_count) return 1;
    dlog("selftest passed: binary log filtered\n");
    return 0;
}
int main(int argc, char **argv) {
    unsigned int seconds = 60;
    if (argc == 2 && !strcmp(argv[1],"--selftest")) return selftest();
    if (argc == 2 && !strcmp(argv[1],"--help")) {
        puts("adsp-f3 [--seconds 1..60] | --selftest"); return 0;
    }
    if (argc == 3 && !strcmp(argv[1],"--seconds")) {
        char *end; errno=0;
        unsigned long value = strtoul(argv[2], &end, 10);
        if (errno || *end || value < 1 || value > 60) return 2;
        seconds = value;
    } else if (argc != 1) {
        fputs("usage: adsp-f3 [--seconds 1..60]\n",stderr); return 2;
    }
    int lockfd=open("/run/lock/negroni-adsp-f3.lock",O_CREAT|O_RDWR|O_CLOEXEC,0600);
    if (lockfd<0 || flock(lockfd,LOCK_EX|LOCK_NB)<0) {
        perror("exclusive diagnostic lock"); if(lockfd>=0)close(lockfd); return 1;
    }
    signal(SIGINT,on_signal); signal(SIGTERM,on_signal); signal(SIGPIPE,SIG_IGN);
    int ctl=serve(DIAG_SVC_ID,64,"CNTL");
    int data=serve(DIAG_SVC_ID,66,"DATA");
    int lookup=start_lookup(DIAG_SVC_ID);
    int status=0;
    struct diag_peer peer={0}; uint32_t diag_id=0;
    if (ctl<0 || data<0 || lookup<0) { status=1; goto cleanup; }
    double deadline=mono_sec()+seconds;
    dlog("F3-only capture for at most %u seconds; no audio or binary logging\n",seconds);
    while (!stop && mono_sec()<deadline) {
        struct pollfd fds[3]={{ctl,POLLIN,0},{data,POLLIN,0},{lookup,POLLIN,0}};
        double remaining=deadline-mono_sec();
        int ms=remaining>1 ? 1000 : (int)(remaining*1000);
        if(ms<1) break;
        if(poll(fds,3,ms)<0) { if(errno==EINTR)continue; perror("poll");status=1;break; }
        for(int i=0;i<3;i++) {
            if(!(fds[i].revents&POLLIN))continue;
            uint8_t buf[MAX_PKT]; struct sockaddr_qrtr from; socklen_t fl=sizeof(from);
            ssize_t n=recvfrom(fds[i].fd,buf,sizeof(buf),MSG_DONTWAIT,
                               (struct sockaddr *)&from,&fl);
            if(n<=0)continue;
            if(i==2) {
                if(from.sq_port==QRTR_PORT_CTRL && (size_t)n>=sizeof(struct qrtr_ctrl_pkt)) {
                    struct qrtr_ctrl_pkt q;memcpy(&q,buf,sizeof(q));
                    if(q.cmd==QRTR_TYPE_NEW_SERVER && q.server.service==DIAG_SVC_ID)
                        dlog("diag instance %u at %u:%u\n",
                             q.server.instance,q.server.node,q.server.port);
                }
            } else if(from.sq_port!=QRTR_PORT_CTRL) {
                if(i==0)control(ctl,&peer,&from,buf,n,&diag_id);
                else if(peer.valid && from.sq_node==peer.addr.sq_node)decode_data(buf,n);
            }
        }
    }
cleanup:
    if(peer.valid) { f3_masks(ctl,&peer,0); binary_off(ctl,&peer.addr); }
    unpublish(ctl,DIAG_SVC_ID,64); unpublish(data,DIAG_SVC_ID,66);
    if(ctl>=0)close(ctl);
    if(data>=0)close(data);
    if(lookup>=0)close(lookup);
    close(lockfd);
    dlog("stopped: F3=%lu discarded_non_F3=%lu; F3 masks disabled and services withdrawn\n",
         f3_count,ignored_count);
    return status;
}
