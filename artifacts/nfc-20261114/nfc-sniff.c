#include <errno.h>
#include <linux/nfc.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

int main(int argc, char **argv)
{
	int seconds = argc > 1 ? atoi(argv[1]) : 20;
	int fd = socket(AF_NFC, SOCK_RAW, NFC_SOCKPROTO_RAW);
	unsigned char buf[512];
	int elapsed = 0;

	if (fd < 0) {
		perror("socket");
		return 1;
	}
	printf("sniff %d s\n", seconds);
	fflush(stdout);
	while (elapsed < seconds) {
		struct pollfd pfd = { .fd = fd, .events = POLLIN };
		int pr = poll(&pfd, 1, 1000);
		int n, i;

		elapsed++;
		if (pr == 0)
			continue;
		if (pr < 0) {
			perror("poll");
			return 1;
		}
		n = recv(fd, buf, sizeof(buf), 0);
		if (n < 0) {
			perror("recv");
			return 1;
		}
		if (n < 2) {
			printf("short %d\n", n);
			continue;
		}
		printf("%s dev %u mt %u :",
		       (buf[1] & 1) ? "TX" : "RX", buf[0], (buf[1] >> 1) & 7);
		for (i = 2; i < n; i++)
			printf(" %02x", buf[i]);
		printf("\n");
		fflush(stdout);
		elapsed--;
	}
	return 0;
}
