/* Fixed-purpose fault worker. Compile once per reviewed WORKER_MODE. */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

#ifndef WORKER_MODE
#define WORKER_MODE 0
#endif

static void __attribute__((unused)) emit(const char *fault, int verified) {
    printf("{\"beast_object_type\":\"mission_fault_evidence\",\"fault\":\"%s\",\"verified\":%s,\"pid\":%ld}\n",
           fault, verified ? "true" : "false", (long)getpid());
    fflush(stdout);
}

int main(void) {
#if WORKER_MODE == 1 /* bounded timeout */
    alarm(1);
    for (;;) pause();
#elif WORKER_MODE == 2 /* OOM: kernel must enforce memory.max */
    size_t block = 1024 * 1024;
    for (;;) {
        void *value = malloc(block);
        if (!value) return 82;
        memset(value, 0xa5, block);
    }
#elif WORKER_MODE == 3 /* bus peer death */
    int pair[2];
    if (socketpair(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0, pair)) return 83;
    pid_t child = fork();
    if (child < 0) return 84;
    if (child == 0) { close(pair[0]); close(pair[1]); _exit(0); }
    close(pair[1]);
    char byte = 0;
    int eof = read(pair[0], &byte, 1) == 0;
    close(pair[0]);
    (void)waitpid(child, NULL, 0);
    emit("bus_peer_death", eof);
    return eof ? 0 : 85;
#elif WORKER_MODE == 4 /* rollback and descriptor cleanup */
    char path[96];
    snprintf(path, sizeof(path), "/tmp/beast-rollback-%ld", (long)getpid());
    int fd = open(path, O_CREAT | O_EXCL | O_RDWR | O_CLOEXEC, 0600);
    if (fd < 0) return 86;
    int wrote = write(fd, "effect", 6) == 6;
    close(fd);
    int removed = unlink(path) == 0 && access(path, F_OK) != 0;
    emit("rollback", wrote && removed);
    return wrote && removed ? 0 : 87;
#elif WORKER_MODE == 5 /* descendant containment */
    pid_t child = fork();
    if (child < 0) return 88;
    if (child == 0) { usleep(100000); _exit(0); }
    emit("descendant_containment", child > 0);
    return waitpid(child, NULL, 0) == child ? 0 : 89;
#else
    emit("invalid_mode", 0);
    return 80;
#endif
}
