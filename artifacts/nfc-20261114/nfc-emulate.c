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

				setsockopt(fd, SOL_NETLINK, NETLINK_ADD_MEMBERSHIP,
					   &gid, sizeof(gid));
			}
		}
	}
	return id;
}

static int cmd(int fd, int fam, int c, uint32_t tm)
{
	unsigned char buf[128];
	struct nlmsghdr *nl = (void *)buf;
	struct genlmsghdr *gh;
	struct nlattr *attr;
	uint32_t index = 0;
	int len;

	memset(buf, 0, sizeof(buf));
	gh = (void *)(nl + 1);
	attr = (void *)(gh + 1);
	nl->nlmsg_type = fam;
	nl->nlmsg_flags = NLM_F_REQUEST | NLM_F_ACK;
	nl->nlmsg_seq = c;
	gh->cmd = c;
	gh->version = NFC_GENL_VERSION;
	len = NLMSG_HDRLEN + sizeof(*gh);
	attr->nla_type = NFC_ATTR_DEVICE_INDEX;
	attr->nla_len = sizeof(*attr) + 4;
	memcpy(attr + 1, &index, 4);
	len += 8;
	if (tm) {
		attr = (void *)((char *)attr + 8);
		attr->nla_type = NFC_ATTR_TM_PROTOCOLS;
		attr->nla_len = sizeof(*attr) + 4;
		memcpy(attr + 1, &tm, 4);
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
	int n;
	struct nlmsghdr *nl;

	if (pr <= 0)
		return pr == 0 ? -ETIMEDOUT : -errno;
	n = recv(fd, buf, sizeof(buf), 0);
	if (n < (int)sizeof(*nl))
		return -EIO;
	nl = (void *)buf;
	if (nl->nlmsg_type == NLMSG_ERROR)
		return ((struct nlmsgerr *)NLMSG_DATA(nl))->error;
	return 0;
}

static void on_nci(const unsigned char *buf, int n)
{
	int i;

	if (n < 3)
		return;
	printf("[%6.2f] %s", now_s(), (buf[1] & 1) ? "TX" : "RX");
	for (i = 2; i < n; i++)
		printf(" %02x", buf[i]);
	printf("\n");
	fflush(stdout);
}

int main(int argc, char **argv)
{
	int seconds = argc > 1 ? atoi(argv[1]) : 25;
	int nl, raw, fam, rc;
	char buf[512];
	struct timespec ts;
	double deadline;
	struct sockaddr_nl local = { .nl_family = AF_NETLINK };

	clock_gettime(CLOCK_MONOTONIC, &ts);
	t0 = ts.tv_sec + ts.tv_nsec / 1e9;
	if (seconds < 5)
		seconds = 5;
	nl = socket(AF_NETLINK, SOCK_RAW, NETLINK_GENERIC);
	raw = socket(AF_NFC, SOCK_RAW, NFC_SOCKPROTO_RAW);
	if (nl < 0 || bind(nl, (void *)&local, sizeof(local)) < 0) {
		perror("netlink");
		return 1;
	}
	fam = family_id(nl);
	if (fam <= 0) {
		printf("family %d\n", fam);
		return 1;
	}
	printf("[%6.2f] dev_up\n", now_s());
	fflush(stdout);
	if (cmd(nl, fam, NFC_CMD_DEV_UP, 0) < 0)
		return 1;
	rc = wait_ack(nl, 12000);
	printf("[%6.2f] dev_up %d (%s)\n", now_s(), rc, strerror(rc < 0 ? -rc : 0));
	fflush(stdout);
	if (rc && rc != -EALREADY)
		goto down;
	if (cmd(nl, fam, NFC_CMD_START_POLL, NFC_PROTO_MIFARE_MASK) < 0)
		goto down;
	rc = wait_ack(nl, 8000);
	printf("[%6.2f] listen %d (%s), %ds. Hold a reader to the back.\n",
	       now_s(), rc, strerror(rc < 0 ? -rc : 0), seconds);
	fflush(stdout);
	if (rc)
		goto down;
	deadline = now_s() + seconds;
	while (now_s() < deadline) {
		struct pollfd pfd = { .fd = raw, .events = POLLIN };
		int n;

		if (raw < 0 || poll(&pfd, 1, 500) <= 0)
			continue;
		n = recv(raw, buf, sizeof(buf), 0);
		if (n > 0)
			on_nci((unsigned char *)buf, n);
	}
	printf("[%6.2f] stop_poll\n", now_s());
	fflush(stdout);
	if (cmd(nl, fam, NFC_CMD_STOP_POLL, 0) == 0)
		printf("[%6.2f] stop %d\n", now_s(), wait_ack(nl, 8000));
down:
	printf("[%6.2f] dev_down\n", now_s());
	fflush(stdout);
	if (cmd(nl, fam, NFC_CMD_DEV_DOWN, 0) == 0)
		printf("[%6.2f] down %d\n", now_s(), wait_ack(nl, 8000));
	fflush(stdout);
	return rc ? 1 : 0;
}
