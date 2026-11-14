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
#include <unistd.h>

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

static int recv_nl(int fd, void *buf, int len, int timeout_ms)
{
	struct pollfd pfd = { .fd = fd, .events = POLLIN };
	int pr = poll(&pfd, 1, timeout_ms);

	if (pr <= 0)
		return pr == 0 ? -ETIMEDOUT : -errno;
	return recv(fd, buf, len, 0);
}

static int family_id(int fd)
{
	struct {
		struct nlmsghdr nl;
		struct genlmsghdr genl;
		struct nlattr attr;
		char name[8];
	} req;
	char buf[4096];
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
	n = recv_nl(fd, buf, sizeof(buf), 1000);
	if (n < 0)
		return n;

	struct nlmsghdr *nl = (void *)buf;

	if (nl->nlmsg_type == NLMSG_ERROR) {
		struct nlmsgerr *e = NLMSG_DATA(nl);

		return e->error;
	}

	struct genlmsghdr *gh = NLMSG_DATA(nl);
	struct nlattr *nla = (void *)(gh + 1);
	int rem = nl->nlmsg_len - NLMSG_HDRLEN - sizeof(*gh);

	for (; nla_ok(nla, rem); nla = nla_next(nla, &rem)) {
		if (nla->nla_type == CTRL_ATTR_FAMILY_ID)
			id = *(uint16_t *)(nla + 1);
	}
	return id;
}

static void dump_attrs(struct nlattr *nla, int rem, const char *tag)
{
	for (; nla_ok(nla, rem); nla = nla_next(nla, &rem)) {
		int t = nla->nla_type & NLA_TYPE_MASK;
		int plen = nla->nla_len - sizeof(*nla);
		unsigned char *p = (unsigned char *)(nla + 1);
		int i;

		printf("%s attr %d len %d:", tag, t, plen);
		for (i = 0; i < plen && i < 48; i++)
			printf(" %02x", p[i]);
		if (t == NFC_ATTR_DEVICE_NAME)
			printf(" name=%.*s", plen, p);
		printf("\n");
	}
}

static int cmd(int fd, int fam, int c, int flags, uint32_t *index,
	       uint32_t protocols)
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
	if (index) {
		attr->nla_type = NFC_ATTR_DEVICE_INDEX;
		attr->nla_len = sizeof(*attr) + 4;
		memcpy(attr + 1, index, 4);
		len += 8;
		attr = (void *)((char *)attr + 8);
	}
	if (protocols) {
		attr->nla_type = NFC_ATTR_PROTOCOLS;
		attr->nla_len = sizeof(*attr) + 4;
		memcpy(attr + 1, &protocols, 4);
		len += 8;
	}
	nl->nlmsg_len = len;
	return send_nl(fd, buf, len);
}

static void print_msg(void *buf, int n)
{
	struct nlmsghdr *nl = buf;

	if (n < (int)sizeof(*nl)) {
		printf("short %d\n", n);
		return;
	}
	if (nl->nlmsg_type == NLMSG_ERROR) {
		struct nlmsgerr *e = NLMSG_DATA(nl);

		printf("result %d (%s)\n", e->error, strerror(e->error < 0 ? -e->error : 0));
		return;
	}
	if (nl->nlmsg_type == NLMSG_DONE) {
		printf("done\n");
		return;
	}
	struct genlmsghdr *gh = NLMSG_DATA(nl);

	printf("msg type %u cmd %u\n", nl->nlmsg_type, gh->cmd);
	dump_attrs((void *)(gh + 1), nl->nlmsg_len - NLMSG_HDRLEN - sizeof(*gh), "a");
}

int main(int argc, char **argv)
{
	int fd = socket(AF_NETLINK, SOCK_RAW, NETLINK_GENERIC);
	char buf[8192];
	int fam, n;
	uint32_t index = 0;
	const char *action = argc > 1 ? argv[1] : "up";

	if (fd < 0) {
		perror("socket");
		return 1;
	}
	struct sockaddr_nl local = { .nl_family = AF_NETLINK };

	if (bind(fd, (void *)&local, sizeof(local)) < 0) {
		perror("bind");
		return 1;
	}
	fam = family_id(fd);
	printf("family %d\n", fam);
	if (fam <= 0)
		return 1;

	if (cmd(fd, fam, NFC_CMD_GET_DEVICE, NLM_F_DUMP, NULL, 0) < 0) {
		perror("get");
		return 1;
	}
	for (;;) {
		n = recv_nl(fd, buf, sizeof(buf), 500);
		if (n == -ETIMEDOUT)
			break;
		if (n < 0) {
			printf("recv %d\n", n);
			break;
		}
		print_msg(buf, n);
		struct nlmsghdr *nl = (void *)buf;

		if (nl->nlmsg_type == NLMSG_DONE || nl->nlmsg_type == NLMSG_ERROR)
			break;
	}

	if (!strcmp(action, "up")) {
		printf("dev_up\n");
		cmd(fd, fam, NFC_CMD_DEV_UP, 0, &index, 0);
		n = recv_nl(fd, buf, sizeof(buf), 12000);
		if (n == -ETIMEDOUT)
			printf("dev_up timeout\n");
		else if (n < 0)
			printf("dev_up recv %d\n", n);
		else
			print_msg(buf, n);
	} else if (!strcmp(action, "down")) {
		printf("dev_down\n");
		cmd(fd, fam, NFC_CMD_DEV_DOWN, 0, &index, 0);
		n = recv_nl(fd, buf, sizeof(buf), 8000);
		if (n == -ETIMEDOUT)
			printf("dev_down timeout\n");
		else
			print_msg(buf, n);
	} else if (!strcmp(action, "poll")) {
		uint32_t protos = 0x1 | 0x2 | 0x4 | 0x8 | 0x10 | 0x20 | 0x40 | 0x80;

		printf("start_poll protos 0x%x\n", protos);
		cmd(fd, fam, NFC_CMD_START_POLL, 0, &index, protos);
		n = recv_nl(fd, buf, sizeof(buf), 8000);
		if (n == -ETIMEDOUT)
			printf("poll cmd timeout\n");
		else
			print_msg(buf, n);
		printf("listening 12s\n");
		for (;;) {
			n = recv_nl(fd, buf, sizeof(buf), 12000);
			if (n == -ETIMEDOUT)
				break;
			if (n < 0)
				break;
			print_msg(buf, n);
		}
	}
	return 0;
}
