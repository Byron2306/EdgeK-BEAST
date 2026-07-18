/* Race-free, descriptor-only worker birth with clone3(CLONE_INTO_CGROUP). */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/sched.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

static int parse_fd(const char *raw) {
    char *end = NULL;
    errno = 0;
    long value = strtol(raw, &end, 10);
    if (errno || !raw[0] || !end || *end || value < 0 || value > INT32_MAX) return -1;
    return (int)value;
}

static int validate_fds(int cgroup_fd, int worker_fd, int gate_fd) {
    struct stat cgroup_stat, worker_stat, gate_stat;
    if (fstat(cgroup_fd, &cgroup_stat) || !S_ISDIR(cgroup_stat.st_mode)) return -1;
    if (fstat(worker_fd, &worker_stat) || !S_ISREG(worker_stat.st_mode)) return -1;
    if (!(worker_stat.st_mode & (S_IXUSR | S_IXGRP | S_IXOTH))) return -1;
    if (fstat(gate_fd, &gate_stat) || !S_ISFIFO(gate_stat.st_mode)) return -1;
    return 0;
}

static int validate_data_fds(int workspace_fd, int manifest_fd) {
    struct stat workspace_stat, manifest_stat;
    if (fstat(workspace_fd, &workspace_stat) || !S_ISDIR(workspace_stat.st_mode)) return -1;
    if (fstat(manifest_fd, &manifest_stat) || !S_ISREG(manifest_stat.st_mode)) return -1;
    return 0;
}

int main(int argc, char **argv) {
    if (argc != 4 && argc != 6) {
        fputs("usage: beast_cgroup_launcher CGROUP_FD WORKER_FD GATE_FD [WORKSPACE_FD MANIFEST_FD]\n", stderr);
        return 64;
    }
    int cgroup_fd = parse_fd(argv[1]);
    int worker_fd = parse_fd(argv[2]);
    int gate_fd = parse_fd(argv[3]);
    int workspace_fd = argc == 6 ? parse_fd(argv[4]) : -1;
    int manifest_fd = argc == 6 ? parse_fd(argv[5]) : -1;
    if (cgroup_fd < 0 || worker_fd < 0 || gate_fd < 0 || validate_fds(cgroup_fd, worker_fd, gate_fd)) {
        fputs("invalid inherited descriptor contract\n", stderr);
        return 65;
    }
    if (argc == 6 && (workspace_fd < 0 || manifest_fd < 0 || validate_data_fds(workspace_fd, manifest_fd))) {
        fputs("invalid inherited cleanup descriptor contract\n", stderr);
        return 66;
    }

    struct clone_args args;
    memset(&args, 0, sizeof(args));
    args.flags = CLONE_INTO_CGROUP;
    args.exit_signal = SIGCHLD;
    args.cgroup = (uint64_t)cgroup_fd;
    pid_t pid = (pid_t)syscall(SYS_clone3, &args, sizeof(args));
    if (pid < 0) {
        fprintf(stderr, "clone3 failed: %s\n", strerror(errno));
        return 70;
    }
    if (pid == 0) {
        char release = 0;
        if (read(gate_fd, &release, 1) != 1 || release != 'R') _exit(71);
        close(gate_fd);
        close(cgroup_fd);
        if (argc == 6) {
            if (dup2(workspace_fd, 10) < 0 || dup2(manifest_fd, 11) < 0) _exit(76);
            if (fcntl(10, F_SETFD, 0) < 0 || fcntl(11, F_SETFD, 0) < 0) _exit(76);
        }
        if (fcntl(worker_fd, F_SETFD, FD_CLOEXEC) < 0) _exit(72);
        char *const child_argv[] = {(char *)"beast-isolated-worker", NULL};
        char *const child_env[] = {NULL};
        execveat(worker_fd, "", child_argv, child_env, AT_EMPTY_PATH);
        _exit(73);
    }

    printf("{\"pid\":%ld,\"placement\":\"clone3_into_cgroup\"}\n", (long)pid);
    fflush(stdout);
    int status = 0;
    if (waitpid(pid, &status, 0) < 0) return 74;
    if (WIFEXITED(status)) return WEXITSTATUS(status);
    if (WIFSIGNALED(status)) return 128 + WTERMSIG(status);
    return 75;
}
