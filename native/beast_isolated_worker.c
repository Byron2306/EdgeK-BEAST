/* Fixed-purpose namespace evidence worker; accepts no arguments or environment. */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/netlink.h>
#include <linux/rtnetlink.h>
#include <net/if.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <sys/ioctl.h>
#include <sched.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mount.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

static int write_text(const char *path, const char *value) {
    int fd = open(path, O_WRONLY | O_CLOEXEC);
    if (fd < 0) return -1;
    size_t length = strlen(value);
    ssize_t written = write(fd, value, length);
    int saved = errno;
    close(fd);
    errno = saved;
    return written == (ssize_t)length ? 0 : -1;
}

static unsigned long namespace_inode(const char *name) {
    char path[64];
    struct stat value;
    if (snprintf(path, sizeof(path), "/proc/self/ns/%s", name) < 0) return 0;
    if (stat(path, &value)) return 0;
    return (unsigned long)value.st_ino;
}

static int non_loopback_interfaces(void) {
    int fd = socket(AF_NETLINK, SOCK_RAW | SOCK_CLOEXEC, NETLINK_ROUTE);
    if (fd < 0) return -1;
    struct {
        struct nlmsghdr header;
        struct ifinfomsg interface;
    } request;
    memset(&request, 0, sizeof(request));
    request.header.nlmsg_len = NLMSG_LENGTH(sizeof(struct ifinfomsg));
    request.header.nlmsg_type = RTM_GETLINK;
    request.header.nlmsg_flags = NLM_F_REQUEST | NLM_F_DUMP;
    request.header.nlmsg_seq = 1;
    request.interface.ifi_family = AF_UNSPEC;
    if (send(fd, &request, request.header.nlmsg_len, 0) < 0) { close(fd); return -1; }
    int count = 0;
    char buffer[8192];
    for (;;) {
        ssize_t length = recv(fd, buffer, sizeof(buffer), 0);
        if (length <= 0) { close(fd); return -1; }
        struct nlmsghdr *message;
        for (message = (struct nlmsghdr *)buffer; NLMSG_OK(message, (unsigned int)length); message = NLMSG_NEXT(message, length)) {
            if (message->nlmsg_type == NLMSG_DONE) { close(fd); return count; }
            if (message->nlmsg_type == NLMSG_ERROR) { close(fd); return -1; }
            if (message->nlmsg_type == RTM_NEWLINK) {
                struct ifinfomsg *interface = NLMSG_DATA(message);
                if (!(interface->ifi_flags & IFF_LOOPBACK)) count++;
            }
        }
    }
}

static int map_user(uid_t uid, gid_t gid) {
    char mapping[64];
    (void)write_text("/proc/self/setgroups", "deny\n");
    if (snprintf(mapping, sizeof(mapping), "0 %lu 1\n", (unsigned long)uid) < 0) return -1;
    if (write_text("/proc/self/uid_map", mapping)) return -1;
    if (snprintf(mapping, sizeof(mapping), "0 %lu 1\n", (unsigned long)gid) < 0) return -1;
    if (write_text("/proc/self/gid_map", mapping)) return -1;
    return setresgid(0, 0, 0) || setresuid(0, 0, 0) ? -1 : 0;
}

static int isolated_loopback_fixture(void) {
    int ctl = socket(AF_INET, SOCK_DGRAM | SOCK_CLOEXEC, 0);
    if (ctl < 0) return 0;
    struct ifreq request;
    memset(&request, 0, sizeof(request));
    strncpy(request.ifr_name, "lo", IFNAMSIZ - 1);
    if (ioctl(ctl, SIOCGIFFLAGS, &request)) { close(ctl); return 0; }
    request.ifr_flags |= IFF_UP | IFF_RUNNING;
    int up = ioctl(ctl, SIOCSIFFLAGS, &request) == 0;
    close(ctl);
    if (!up) return 0;
    int server = socket(AF_INET, SOCK_STREAM | SOCK_CLOEXEC, 0);
    if (server < 0) return 0;
    struct sockaddr_in address;
    memset(&address, 0, sizeof(address));
    address.sin_family = AF_INET;
    address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    address.sin_port = 0;
    if (bind(server, (struct sockaddr *)&address, sizeof(address)) || listen(server, 1)) { close(server); return 0; }
    socklen_t length = sizeof(address);
    if (getsockname(server, (struct sockaddr *)&address, &length)) { close(server); return 0; }
    int client = socket(AF_INET, SOCK_STREAM | SOCK_CLOEXEC, 0);
    if (client < 0 || connect(client, (struct sockaddr *)&address, sizeof(address))) { if (client >= 0) close(client); close(server); return 0; }
    int peer = accept4(server, NULL, NULL, SOCK_CLOEXEC);
    int verified = peer >= 0 && write(client, "R", 1) == 1;
    char value = 0;
    verified = verified && read(peer, &value, 1) == 1 && value == 'R';
    if (peer >= 0) close(peer);
    close(client); close(server);
    return verified;
}

static int evidence_child(int routes, const char *root) {
    if (chroot(root) || chdir("/")) return 85;
    if (mount("proc", "/proc", "proc", MS_NOSUID | MS_NODEV | MS_NOEXEC, NULL)) return 86;
    int secrets_denied = access("/etc/shadow", F_OK) != 0 && access("/home", F_OK) != 0;
    int loopback_fixture = isolated_loopback_fixture();
    printf(
        "{\"beast_object_type\":\"isolated_worker_evidence\","
        "\"version\":\"1.0\",\"pid\":%ld,\"uid\":%ld,\"gid\":%ld,"
        "\"namespace_inodes\":{\"mnt\":%lu,\"pid\":%lu,\"net\":%lu,\"user\":%lu},"
        "\"non_loopback_interface_count\":%d,\"private_proc_mounted\":true,"
        "\"filesystem_root_isolated\":true,\"secrets_denied\":%s,"
        "\"isolated_loopback_service_verified\":%s,\"ambient_network_denied\":%s}\n",
        (long)getpid(), (long)getuid(), (long)getgid(),
        namespace_inode("mnt"), namespace_inode("pid"), namespace_inode("net"), namespace_inode("user"),
        routes, secrets_denied ? "true" : "false", loopback_fixture ? "true" : "false",
        routes == 0 ? "true" : "false"
    );
    fflush(stdout);
    return 0;
}

int main(int argc, char **argv) {
    (void)argv;
    if (argc != 1) return 80;
    uid_t uid = getuid();
    gid_t gid = getgid();
    if (unshare(CLONE_NEWUSER)) return 81;
    if (map_user(uid, gid)) return 82;
    if (unshare(CLONE_NEWNS | CLONE_NEWNET | CLONE_NEWPID)) return 83;
    if (mount(NULL, "/", NULL, MS_REC | MS_PRIVATE, NULL)) return 84;
    int routes = non_loopback_interfaces();
    if (routes < 0) return 87;
    char root[128], proc_path[160];
    if (snprintf(root, sizeof(root), "/tmp/beast-isolated-root-%ld", (long)getpid()) < 0) return 88;
    if (snprintf(proc_path, sizeof(proc_path), "%s/proc", root) < 0) return 88;
    if (mkdir(root, 0700) || mount("tmpfs", root, "tmpfs", MS_NOSUID | MS_NODEV | MS_NOEXEC, "size=16m") || mkdir(proc_path, 0555)) return 88;
    pid_t child = fork();
    if (child < 0) return 89;
    if (child == 0) _exit(evidence_child(routes, root));
    int status = 0;
    if (waitpid(child, &status, 0) < 0) return 90;
    int cleanup = umount2(proc_path, MNT_DETACH) == 0;
    cleanup = umount2(root, MNT_DETACH) == 0 && cleanup;
    cleanup = rmdir(root) == 0 && cleanup;
    printf("{\"beast_object_type\":\"isolated_worker_cleanup\",\"root_cleanup_confirmed\":%s}\n", cleanup ? "true" : "false");
    fflush(stdout);
    if (!cleanup) return 91;
    return WIFEXITED(status) ? WEXITSTATUS(status) : 92;
}
