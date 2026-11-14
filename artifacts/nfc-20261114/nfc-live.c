#include <errno.h>
#include <linux/genetlink.h>
#include <linux/netlink.h>
#include <linux/nfc.h>
#include <poll.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>

static double t0;

static double now_s(void)
{
	struct timespec ts;

	clock_gettime(CLOCK_MONOTONIC, &ts);
	return ts.tv_sec + ts.tv_nsec / 1e9 - t0;
}

static void hex(const unsigned char *p, int n)
{
	int i;

	for (i = 0; i < n; i++)
		printf(" %02x", p[i]);
}

static int nla_ok(const struct nlattr *nla, int len)
{
	return len >= (int)sizeof(*nla) && nla->nla_len >= sizeof(*nla) &&
	       nla->nla_len <= len;
}

static struct nlattr *nla_next(const struct nlattr *nla, int *len)
{
	int align = (nla->nla_len + 3) & ~3;

	*len -= align;
	return (struct nlattr *)((char *)nla + align);
}

static int send_nl(int fd, void *buf, int len)
{
	struct sockaddr_nl sa = { .nl_family = AF_NETLINK };
	struct iovec iov = { .iov_base = buf, .iov_len = len };
	struct msghdr msg = {
		.msg_name = &sa,
		.msg_namelen = sizeof(sa),
		.msg_iov = &iov,
		.msg_iovlen = 1,
	};

	return sendmsg(fd, &msg, 0);
}

static int family_id(int fd)
{
	struct {
		struct nlmsghdr nl;
		struct genlmsghdr genl;
		struct nlattr attr;
		char name[4];
	} req;
	char buf[8192];
	int n, id = -1;

	memset(&req, 0, sizeof(req));
	req.nl.nlmsg_len = sizeof(req);
	req.nl.nlmsg_type = GENL_ID_CTRL;
	req.nl.nlmsg_flags = NLM_F_REQUEST;
	req.nl.nlmsg_seq = 1;
	req.genl.cmd = CTRL_CMD_GETFAMILY;
	req.genl.version = 1;
	req.attr.nla_type = CTRL_ATTR_FAMILY_NAME;
	req.attr.nla_len = sizeof(struct nlattr) + 4;
	memcpy(req.name, "nfc", 4);
	if (send_nl(fd, &req, sizeof(req)) < 0)
		return -errno;
	n = recv(fd, buf, sizeof(buf), 0);
	if (n < 0)
		return -errno;

	struct nlmsghdr *nl = (void *)buf;

	if (nl->nlmsg_type == NLMSG_ERROR)
		return ((struct nlmsgerr *)NLMSG_DATA(nl))->error;

	struct genlmsghdr *gh = NLMSG_DATA(nl);
	struct nlattr *nla = (void *)(gh + 1);
	int rem = nl->nlmsg_len - NLMSG_HDRLEN - sizeof(*gh);

	for (; nla_ok(nla, rem); nla = nla_next(nla, &rem)) {
		int t = nla->nla_type & NLA_TYPE_MASK;

		if (t == CTRL_ATTR_FAMILY_ID)
			id = *(uint16_t *)(nla + 1);
		if (t != CTRL_ATTR_MCAST_GROUPS)
			continue;

		struct nlattr *grp = (void *)(nla + 1);
		int grem = nla->nla_len - sizeof(*nla);

		for (; nla_ok(grp, grem); grp = nla_next(grp, &grem)) {
			struct nlattr *a = (void *)(grp + 1);
			int arem = grp->nla_len - sizeof(*grp);

			for (; nla_ok(a, arem); a = nla_next(a, &arem)) {
				if ((a->nla_type & NLA_TYPE_MASK) != CTRL_ATTR_MCAST_GRP_ID)
					continue;
				uint32_t gid = *(uint32_t *)(a + 1);

				if (setsockopt(fd, SOL_NETLINK, NETLINK_ADD_MEMBERSHIP,
					       &gid, sizeof(gid)) < 0)
					perror("membership");
				else
					printf("[%6.2f] joined group %u\n", now_s(), gid);
			}
		}
	}
	return id;
}

static int cmd(int fd, int fam, int c, int flags, uint32_t index, uint32_t protocols)
{
	unsigned char buf[128];
	struct nlmsghdr *nl = (void *)buf;
	struct genlmsghdr *gh;
	struct nlattr *attr;
	int len;

	memset(buf, 0, sizeof(buf));
	gh = (void *)(nl + 1);
	attr = (void *)(gh + 1);
	nl->nlmsg_type = fam;
	nl->nlmsg_flags = NLM_F_REQUEST | NLM_F_ACK | flags;
	nl->nlmsg_seq = c;
	gh->cmd = c;
	gh->version = NFC_GENL_VERSION;
	len = NLMSG_HDRLEN + sizeof(*gh);
	attr->nla_type = NFC_ATTR_DEVICE_INDEX;
	attr->nla_len = sizeof(*attr) + 4;
	memcpy(attr + 1, &index, 4);
	len += 8;
	attr = (void *)((char *)attr + 8);
	if (protocols) {
		attr->nla_type = NFC_ATTR_PROTOCOLS;
		attr->nla_len = sizeof(*attr) + 4;
		memcpy(attr + 1, &protocols, 4);
		len += 8;
	}
	nl->nlmsg_len = len;
	return send_nl(fd, buf, len);
}

static int wait_ack(int fd, int timeout_ms)
{
	char buf[4096];
	struct pollfd pfd = { .fd = fd, .events = POLLIN };
	int pr = poll(&pfd, 1, timeout_ms);

	if (pr <= 0)
		return pr == 0 ? -ETIMEDOUT : -errno;
	int n = recv(fd, buf, sizeof(buf), 0);

	if (n < (int)sizeof(struct nlmsghdr))
		return -EIO;
	struct nlmsghdr *nl = (void *)buf;

	if (nl->nlmsg_type == NLMSG_ERROR)
		return ((struct nlmsgerr *)NLMSG_DATA(nl))->error;
	return 0;
}

static const char *proto_name(uint32_t mask)
{
	if (mask & NFC_PROTO_MIFARE_MASK)
		return "mifare/type2";
	if (mask & NFC_PROTO_ISO14443_MASK)
		return "iso14443-4a";
	if (mask & NFC_PROTO_ISO14443_B_MASK)
		return "iso14443-b";
	if (mask & NFC_PROTO_FELICA_MASK)
		return "felica";
	if (mask & NFC_PROTO_ISO15693_MASK)
		return "iso15693";
	if (mask & NFC_PROTO_JEWEL_MASK)
		return "jewel";
	if (mask & NFC_PROTO_NFC_DEP_MASK)
		return "nfc-dep";
	return "other";
}

static int pick_proto(uint32_t mask, unsigned sel_res)
{
	if ((mask & NFC_PROTO_ISO14443_MASK) && (sel_res & 0x20))
		return NFC_PROTO_ISO14443;
	if (mask & NFC_PROTO_MIFARE_MASK)
		return NFC_PROTO_MIFARE;
	if (mask & NFC_PROTO_ISO14443_MASK)
		return NFC_PROTO_ISO14443;
	if (mask & NFC_PROTO_ISO14443_B_MASK)
		return NFC_PROTO_ISO14443_B;
	if (mask & NFC_PROTO_FELICA_MASK)
		return NFC_PROTO_FELICA;
	if (mask & NFC_PROTO_ISO15693_MASK)
		return NFC_PROTO_ISO15693;
	if (mask & NFC_PROTO_JEWEL_MASK)
		return NFC_PROTO_JEWEL;
	return 0;
}

static int xchg(int fd, const unsigned char *tx, int txlen, unsigned char *rx, int rxmax)
{
	struct pollfd pfd = { .fd = fd, .events = POLLIN };
	int n;

	printf("[%6.2f] tag tx", now_s());
	hex(tx, txlen);
	printf("\n");
	fflush(stdout);
	if (send(fd, tx, txlen, 0) != txlen)
		return -errno;
	if (poll(&pfd, 1, 1500) <= 0)
		return -ETIMEDOUT;
	n = recv(fd, rx, rxmax, 0);
	if (n < 0)
		return -errno;
	printf("[%6.2f] tag rx", now_s());
	hex(rx, n);
	printf("\n");
	fflush(stdout);
	return n;
}

static void print_ndef(const unsigned char *p, int n)
{
	int i = 0;

	while (i + 2 < n) {
		unsigned char tnf = p[i] & 0x07;
		int sr = p[i] & 0x10;
		int il = p[i] & 0x08;
		int me = p[i] & 0x40;
		int tlen, plen, idlen = 0;
		const unsigned char *type, *pay;

		if (p[i] == 0xfe || p[i] == 0x00)
			break;
		i++;
		if (i >= n)
			break;
		tlen = p[i++];
		if (sr) {
			if (i >= n)
				break;
			plen = p[i++];
		} else {
			if (i + 4 > n)
				break;
			plen = (p[i] << 24) | (p[i + 1] << 16) | (p[i + 2] << 8) | p[i + 3];
			i += 4;
		}
		if (il) {
			if (i >= n)
				break;
			idlen = p[i++];
		}
		if (i + tlen + idlen + plen > n)
			break;
		type = p + i;
		i += tlen + idlen;
		pay = p + i;
		i += plen;
		if (tnf == 0x01 && tlen == 1 && type[0] == 'T' && plen >= 1) {
			int lang = pay[0] & 0x3f;

			if (1 + lang <= plen)
				printf("[%6.2f] NDEF text: %.*s\n", now_s(),
				       plen - 1 - lang, pay + 1 + lang);
		} else if (tnf == 0x01 && tlen == 1 && type[0] == 'U' && plen >= 1) {
			static const char *prefix[] = {
				"", "http://www.", "https://www.", "http://", "https://",
				"tel:", "mailto:", "ftp://anonymous:anonymous@", "ftp://ftp.",
				"ftps://", "sftp://", "smb://", "nfs://", "ftp://", "dav://",
				"news:", "telnet://", "imap:", "rtsp://", "urn:", "pop:",
				"sip:", "sips:", "tftp:", "btspp://", "btl2cap://",
				"btgoep://", "tcpobex://", "irdaobex://", "file://",
				"urn:epc:id:", "urn:epc:tag:", "urn:epc:pat:", "urn:epc:raw:",
				"urn:epc:", "urn:nfc:"
			};
			unsigned code = pay[0];
			const char *pre = code < sizeof(prefix) / sizeof(prefix[0]) ? prefix[code] : "";

			printf("[%6.2f] NDEF uri: %s%.*s\n", now_s(), pre, plen - 1, pay + 1);
		} else {
			printf("[%6.2f] NDEF tnf %u type %.*s len %d\n", now_s(), tnf,
			       tlen, type, plen);
		}
		fflush(stdout);
		if (me)
			break;
	}
}

static void read_tag(uint32_t index, uint32_t protos, unsigned sel_res)
{
	int proto = pick_proto(protos, sel_res);
	int fd, n;
	unsigned char rx[256];
	struct sockaddr_nfc addr = {
		.sa_family = AF_NFC,
		.dev_idx = 0,
		.target_idx = index,
		.nfc_protocol = proto,
	};

	printf("[%6.2f] activate idx %u proto %d (%s) sel_res 0x%02x\n",
	       now_s(), index, proto, proto_name(protos), sel_res);
	fflush(stdout);
	if (!proto)
		return;
	fd = socket(AF_NFC, SOCK_SEQPACKET, NFC_SOCKPROTO_RAW);
	if (fd < 0) {
		perror("seqpacket");
		return;
	}
	if (connect(fd, (void *)&addr, sizeof(addr)) < 0) {
		printf("[%6.2f] activate failed: %s\n", now_s(), strerror(errno));
		fflush(stdout);
		close(fd);
		return;
	}
	printf("[%6.2f] activated\n", now_s());
	fflush(stdout);

	if (proto == NFC_PROTO_MIFARE) {
		static const unsigned char pages[] = { 0x00, 0x04, 0x08, 0x0c };
		unsigned char all[64];
		int got = 0, k;

		for (k = 0; k < 4 && got < (int)sizeof(all); k++) {
			unsigned char tx[2] = { 0x30, pages[k] };

			n = xchg(fd, tx, 2, rx, sizeof(rx));
			if (n < 5)
				break;
			memcpy(all + got, rx + 1, 16);
			got += 16;
		}
		if (got >= 16) {
			int i = 16;

			printf("[%6.2f] type2 %d bytes\n", now_s(), got);
			while (i < got) {
				if (all[i] == 0x00) {
					i++;
					continue;
				}
				if (all[i] == 0xfe || all[i] == 0x00)
					break;
				if (all[i] == 0x03 && i + 2 < got) {
					int len = all[i + 1];
					int start = i + 2;

					if (len == 0xff && i + 4 < got) {
						len = (all[i + 2] << 8) | all[i + 3];
						start = i + 4;
					}
					if (start + len <= got)
						print_ndef(all + start, len);
					else
						printf("[%6.2f] NDEF tlv len %d, have %d\n",
						       now_s(), len, got - start);
					break;
				}
				if (i + 1 >= got)
					break;
				i += 2 + all[i + 1];
			}
		}
	} else if (proto == NFC_PROTO_ISO14443) {
		static const unsigned char sel[] = {
			0x00, 0xa4, 0x04, 0x00, 0x07,
			0xd2, 0x76, 0x00, 0x00, 0x85, 0x01, 0x01, 0x00
		};
		unsigned char cc[2] = { 0xe1, 0x03 };
		unsigned char file[2];
		unsigned char apdu[5] = { 0x00, 0xb0, 0x00, 0x00, 0x0f };

		n = xchg(fd, sel, sizeof(sel), rx, sizeof(rx));
		if (n >= 3 && rx[n - 2] == 0x90 && rx[n - 1] == 0x00) {
			unsigned char selcc[7] = { 0x00, 0xa4, 0x00, 0x0c, 0x02, cc[0], cc[1] };

			n = xchg(fd, selcc, sizeof(selcc), rx, sizeof(rx));
			if (n >= 3 && rx[n - 2] == 0x90 && rx[n - 1] == 0x00) {
				n = xchg(fd, apdu, sizeof(apdu), rx, sizeof(rx));
				if (n >= 17 && rx[n - 2] == 0x90) {
					file[0] = rx[1 + 9];
					file[1] = rx[1 + 10];
					printf("[%6.2f] ndef file %02x%02x\n", now_s(), file[0], file[1]);
					unsigned char selfile[7] = {
						0x00, 0xa4, 0x00, 0x0c, 0x02, file[0], file[1]
					};
					n = xchg(fd, selfile, sizeof(selfile), rx, sizeof(rx));
					if (n >= 3 && rx[n - 2] == 0x90) {
						apdu[4] = 0x20;
						n = xchg(fd, apdu, sizeof(apdu), rx, sizeof(rx));
						if (n > 4 && rx[n - 2] == 0x90) {
							int nlen = (rx[1] << 8) | rx[2];

							if (nlen > 0 && nlen <= n - 5)
								print_ndef(rx + 3, nlen);
							else
								printf("[%6.2f] ndef nlen %d\n", now_s(), nlen);
						}
					}
				}
			}
		} else {
			printf("[%6.2f] not an NDEF type-4 tag\n", now_s());
		}
	}
	close(fd);
	fflush(stdout);
}

static void on_nci(const unsigned char *buf, int n)
{
	const unsigned char *p;
	int plen, tech, idlen;

	if (n < 5)
		return;
	printf("[%6.2f] %s", now_s(), (buf[1] & 1) ? "TX" : "RX");
	hex(buf + 2, n - 2);
	printf("\n");
	if ((buf[1] & 1) || buf[2] != 0x61 || buf[3] != 0x03 || n < 9)
		return;
	p = buf + 5;
	plen = buf[4];
	if (plen < 4 || 5 + plen > n)
		return;
	tech = p[2];
	if (tech != 0x00)
		return;
	if (p[3] < 3)
		return;
	idlen = p[6];
	if (idlen < 4 || idlen > 10 || 7 + idlen > plen)
		return;
	printf("[%6.2f] NFC-A UID", now_s());
	hex(p + 7, idlen);
	printf("\n");
	fflush(stdout);
}

int main(int argc, char **argv)
{
	int seconds = argc > 1 ? atoi(argv[1]) : 30;
	int nl, raw, fam, asked = 0;
	uint32_t dev_idx = 0, target_idx = 0, protos = 0;
	unsigned sel_res = 0;
	int have = 0, read_done = 0;
	char buf[8192];
	struct timespec ts;
	double deadline;

	clock_gettime(CLOCK_MONOTONIC, &ts);
	t0 = ts.tv_sec + ts.tv_nsec / 1e9;
	if (seconds < 5)
		seconds = 5;
	nl = socket(AF_NETLINK, SOCK_RAW, NETLINK_GENERIC);
	raw = socket(AF_NFC, SOCK_RAW, NFC_SOCKPROTO_RAW);
	if (nl < 0) {
		perror("netlink");
		return 1;
	}
	struct sockaddr_nl local = { .nl_family = AF_NETLINK };

	if (bind(nl, (void *)&local, sizeof(local)) < 0) {
		perror("bind");
		return 1;
	}
	fam = family_id(nl);
	printf("[%6.2f] family %d raw %d\n", now_s(), fam, raw);
	fflush(stdout);
	if (fam <= 0)
		return 1;
	printf("[%6.2f] dev_up\n", now_s());
	fflush(stdout);
	if (cmd(nl, fam, NFC_CMD_DEV_UP, 0, dev_idx, 0) < 0) {
		perror("up");
		return 1;
	}
	int rc = wait_ack(nl, 12000);

	printf("[%6.2f] dev_up result %d (%s)\n", now_s(), rc, strerror(rc < 0 ? -rc : 0));
	fflush(stdout);
	if (rc && rc != -EALREADY)
		goto down;
	if (cmd(nl, fam, NFC_CMD_START_POLL, 0, dev_idx, 0xfe) < 0) {
		perror("poll");
		goto down;
	}
	rc = wait_ack(nl, 8000);
	printf("[%6.2f] poll result %d (%s), listening %ds\n", now_s(), rc,
	       strerror(rc < 0 ? -rc : 0), seconds);
	fflush(stdout);
	if (rc)
		goto down;
	deadline = now_s() + seconds;
	double next_beat = now_s() + 5;

	while (now_s() < deadline && !read_done) {
		if (now_s() >= next_beat) {
			printf("[%6.2f] still listening\n", now_s());
			fflush(stdout);
			next_beat += 5;
		}
		struct pollfd pfd[2] = {
			{ .fd = nl, .events = POLLIN },
			{ .fd = raw, .events = POLLIN },
		};
		int pr = poll(pfd, raw >= 0 ? 2 : 1, 500);

		if (pr < 0)
			break;
		if (pfd[0].revents & POLLIN) {
			int n = recv(nl, buf, sizeof(buf), 0);
			struct nlmsghdr *msg = (void *)buf;

			for (; n > 0 && NLMSG_OK(msg, n); msg = NLMSG_NEXT(msg, n)) {
				if (msg->nlmsg_type == NLMSG_ERROR || msg->nlmsg_type == NLMSG_DONE) {
					if (asked && msg->nlmsg_type == NLMSG_DONE && have && !read_done) {
						read_tag(target_idx, protos, sel_res);
						read_done = 1;
					}
					continue;
				}
				if (msg->nlmsg_type != fam)
					continue;
				struct genlmsghdr *gh = NLMSG_DATA(msg);
				struct nlattr *nla = (void *)(gh + 1);
				int rem = msg->nlmsg_len - NLMSG_HDRLEN - sizeof(*gh);

				printf("[%6.2f] event cmd %u\n", now_s(), gh->cmd);
				for (; nla_ok(nla, rem); nla = nla_next(nla, &rem)) {
					int t = nla->nla_type & NLA_TYPE_MASK;
					int plen = nla->nla_len - sizeof(*nla);
					unsigned char *p = (unsigned char *)(nla + 1);

					if (t == NFC_ATTR_TARGET_INDEX && plen >= 4)
						target_idx = *(uint32_t *)p;
					if (t == NFC_ATTR_PROTOCOLS && plen >= 4) {
						protos = *(uint32_t *)p;
						have = 1;
						printf("[%6.2f] protocols 0x%x %s\n", now_s(),
						       protos, proto_name(protos));
					}
					if (t == NFC_ATTR_TARGET_SEL_RES && plen >= 1)
						sel_res = p[0];
					if (t == NFC_ATTR_TARGET_NFCID1 ||
					    t == NFC_ATTR_TARGET_SENSB_RES ||
					    t == NFC_ATTR_TARGET_SENSF_RES ||
					    t == NFC_ATTR_TARGET_ISO15693_UID) {
						printf("[%6.2f] id attr %d", now_s(), t);
						hex(p, plen);
						printf("\n");
						have = 1;
					}
				}
				fflush(stdout);
				if (gh->cmd == NFC_EVENT_TARGETS_FOUND && !asked) {
					asked = 1;
					printf("[%6.2f] reading target\n", now_s());
					fflush(stdout);
					cmd(nl, fam, NFC_CMD_GET_TARGET, NLM_F_DUMP, dev_idx, 0);
				}
			}
		}
		if (raw >= 0 && (pfd[1].revents & POLLIN)) {
			int n = recv(raw, buf, sizeof(buf), 0);

			if (n > 0)
				on_nci((unsigned char *)buf, n);
		}
	}
	if (!read_done)
		printf("[%6.2f] no tag\n", now_s());
down:
	printf("[%6.2f] stop_poll\n", now_s());
	fflush(stdout);
	if (cmd(nl, fam, NFC_CMD_STOP_POLL, 0, dev_idx, 0) == 0)
		printf("[%6.2f] stop_poll result %d\n", now_s(), wait_ack(nl, 8000));
	printf("[%6.2f] dev_down\n", now_s());
	fflush(stdout);
	if (cmd(nl, fam, NFC_CMD_DEV_DOWN, 0, dev_idx, 0) == 0)
		printf("[%6.2f] down result %d\n", now_s(), wait_ack(nl, 8000));
	fflush(stdout);
	return 0;
}
