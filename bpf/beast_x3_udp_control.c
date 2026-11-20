/* Native userspace control for the isolated X3 packet-path benchmark. */
#include <arpa/inet.h>
#include <errno.h>
#include <signal.h>
#include <stdio.h>
#include <sys/socket.h>
#include <unistd.h>

static volatile sig_atomic_t stopping;
static void stop(int sig) { (void)sig; stopping = 1; }

int main(void) {
    int fd = socket(AF_INET, SOCK_DGRAM, 0);
    struct sockaddr_in addr = {.sin_family = AF_INET, .sin_port = htons(20397)};
    if (fd < 0 || inet_pton(AF_INET, "10.203.0.2", &addr.sin_addr) != 1 ||
        bind(fd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        perror("UDP control bind");
        return 1;
    }
    struct sigaction sa = {.sa_handler = stop};
    if (sigemptyset(&sa.sa_mask) < 0 || sigaction(SIGTERM, &sa, NULL) < 0) {
        perror("UDP control signal setup");
        return 1;
    }
    fputs("BEAST_READY {\"observed_mode\":\"udp\"}\n", stderr);
    fflush(stderr);
    unsigned long long rx = 0, tx = 0;
    while (!stopping) {
        unsigned char data[2048];
        struct sockaddr_in peer;
        socklen_t size = sizeof(peer);
        ssize_t count = recvfrom(fd, data, sizeof(data), 0, (struct sockaddr *)&peer, &size);
        if (count < 0) {
            if (errno == EINTR) continue;
            perror("UDP control recvfrom");
            return 1;
        }
        rx++;
        if (sendto(fd, data, (size_t)count, 0, (struct sockaddr *)&peer, size) == count) tx++;
    }
    printf("{\"packets_rx\":%llu,\"packets_tx\":%llu}\n", rx, tx);
    close(fd);
    return 0;
}
