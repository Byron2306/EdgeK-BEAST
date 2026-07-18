/* Fixed-purpose descriptor-only cleanup worker for destructive held-out replay. */
#define _GNU_SOURCE
#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/netlink.h>
#include <linux/rtnetlink.h>
#include <net/if.h>
#include <openssl/evp.h>
#include <sched.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mount.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

#define WORKSPACE_FD 10
#define MANIFEST_FD 11
#define MAX_ENTRIES 64

struct entry { char path[512]; unsigned long long dev, ino, size, mtime_ns; char sha[65]; };

static int write_text(const char *path, const char *value) {
    int fd=open(path,O_WRONLY|O_CLOEXEC); if(fd<0)return -1;
    ssize_t n=write(fd,value,strlen(value)); int saved=errno; close(fd); errno=saved;
    return n==(ssize_t)strlen(value)?0:-1;
}
static int map_user(uid_t uid,gid_t gid){char b[64];(void)write_text("/proc/self/setgroups","deny\n");
    snprintf(b,sizeof(b),"0 %lu 1\n",(unsigned long)uid);if(write_text("/proc/self/uid_map",b))return -1;
    snprintf(b,sizeof(b),"0 %lu 1\n",(unsigned long)gid);if(write_text("/proc/self/gid_map",b))return -1;
    return setresgid(0,0,0)||setresuid(0,0,0)?-1:0;}
static unsigned long ns_inode(const char *name){char p[64];struct stat s;snprintf(p,sizeof(p),"/proc/self/ns/%s",name);return stat(p,&s)?0:(unsigned long)s.st_ino;}

static int non_loopback_interfaces(void){
    int fd=socket(AF_NETLINK,SOCK_RAW|SOCK_CLOEXEC,NETLINK_ROUTE);if(fd<0)return -1;
    struct {struct nlmsghdr h;struct ifinfomsg i;} req;memset(&req,0,sizeof(req));
    req.h.nlmsg_len=NLMSG_LENGTH(sizeof(struct ifinfomsg));req.h.nlmsg_type=RTM_GETLINK;req.h.nlmsg_flags=NLM_F_REQUEST|NLM_F_DUMP;req.h.nlmsg_seq=1;
    if(send(fd,&req,req.h.nlmsg_len,0)<0){close(fd);return -1;}int count=0;char buf[8192];
    for(;;){ssize_t len=recv(fd,buf,sizeof(buf),0);if(len<=0){close(fd);return -1;}
        for(struct nlmsghdr *m=(struct nlmsghdr*)buf;NLMSG_OK(m,(unsigned int)len);m=NLMSG_NEXT(m,len)){
            if(m->nlmsg_type==NLMSG_DONE){close(fd);return count;}if(m->nlmsg_type==NLMSG_ERROR){close(fd);return -1;}
            if(m->nlmsg_type==RTM_NEWLINK){struct ifinfomsg *i=NLMSG_DATA(m);if(!(i->ifi_flags&IFF_LOOPBACK))count++;}}}}
static int loopback_fixture(void){int ctl=socket(AF_INET,SOCK_DGRAM|SOCK_CLOEXEC,0);if(ctl<0)return 0;struct ifreq r;memset(&r,0,sizeof(r));strncpy(r.ifr_name,"lo",IFNAMSIZ-1);
    if(ioctl(ctl,SIOCGIFFLAGS,&r)){close(ctl);return 0;}r.ifr_flags|=IFF_UP|IFF_RUNNING;int ok=ioctl(ctl,SIOCSIFFLAGS,&r)==0;close(ctl);return ok;}

static int protected_path(const char *path){
    if(!path[0]||path[0]=='/'||strstr(path,".."))return 1;
    char copy[512];snprintf(copy,sizeof(copy),"%s",path);
    char *save=NULL;for(char *p=strtok_r(copy,"/",&save);p;p=strtok_r(NULL,"/",&save))
        if(!strcmp(p,".git")||!strcmp(p,".beast")||!strcmp(p,".ssh")||!strcmp(p,"secrets")||!strcmp(p,"credentials")||!strcmp(p,"source"))return 1;
    return 0;
}
static int open_parent(int root,const char *path,char base[512]){
    char copy[512];snprintf(copy,sizeof(copy),"%s",path);char *last=strrchr(copy,'/');int current=dup(root);if(current<0)return -1;
    if(!last){snprintf(base,512,"%s",copy);return current;}*last='\0';snprintf(base,512,"%s",last+1);
    char *save=NULL;for(char *p=strtok_r(copy,"/",&save);p;p=strtok_r(NULL,"/",&save)){int next=openat(current,p,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);close(current);if(next<0)return -1;current=next;}return current;
}
static int sha_file(int fd,char out[65]){EVP_MD_CTX *ctx=EVP_MD_CTX_new();if(!ctx)return -1;unsigned char digest[32];unsigned int n=0;char b[65536];ssize_t got=0;int ok=EVP_DigestInit_ex(ctx,EVP_sha256(),NULL)==1;
    while(ok&&(got=read(fd,b,sizeof(b)))>0){ok=EVP_DigestUpdate(ctx,b,(size_t)got)==1;}
    if(got<0){ok=0;}
    if(ok){ok=EVP_DigestFinal_ex(ctx,digest,&n)==1&&n==32;}
    EVP_MD_CTX_free(ctx);if(!ok)return -1;
    for(unsigned i=0;i<32;i++){snprintf(out+i*2,3,"%02x",digest[i]);}out[64]='\0';return 0;}
static unsigned long long mtime_ns(struct stat *s){return (unsigned long long)s->st_mtim.tv_sec*1000000000ULL+(unsigned long long)s->st_mtim.tv_nsec;}
static int validate_entry(struct entry *e){char base[512],sha[65];int parent=open_parent(WORKSPACE_FD,e->path,base);if(parent<0)return -1;int fd=openat(parent,base,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);close(parent);if(fd<0)return -1;
    struct stat s;int ok=!fstat(fd,&s)&&S_ISREG(s.st_mode)&&s.st_nlink==1&&(unsigned long long)s.st_dev==e->dev&&(unsigned long long)s.st_ino==e->ino&&(unsigned long long)s.st_size==e->size&&mtime_ns(&s)==e->mtime_ns&&!sha_file(fd,sha)&&!strcmp(sha,e->sha);close(fd);return ok?0:-1;}

static int cleanup_child(const char *root,int routes){
    if(chroot(root)||chdir("/")||mount("proc","/proc","proc",MS_NOSUID|MS_NODEV|MS_NOEXEC,NULL))return 90;
    FILE *mf=fdopen(dup(MANIFEST_FD),"r");if(!mf)return 91;char *line=NULL;size_t cap=0;char manifest_digest[80]={0};int expected=0;unsigned long long expected_bytes=0;
    if(getline(&line,&cap,mf)<0||sscanf(line,"BEAST_DISK_V1\t%d\t%llu\t%79s",&expected,&expected_bytes,manifest_digest)!=3||expected<1||expected>MAX_ENTRIES)return 92;
    struct entry entries[MAX_ENTRIES];int count=0;unsigned long long total=0;
    while(count<expected&&getline(&line,&cap,mf)>=0){struct entry *e=&entries[count];memset(e,0,sizeof(*e));
        if(sscanf(line,"%511[^\t]\t%llu\t%llu\t%llu\t%llu\t%64s",e->path,&e->dev,&e->ino,&e->size,&e->mtime_ns,e->sha)!=6||protected_path(e->path)||strlen(e->sha)!=64)return 93;
        if(validate_entry(e))return 94;
        total+=e->size;count++;}
    free(line);fclose(mf);if(count!=expected||total!=expected_bytes)return 95;
    char qname[96];snprintf(qname,sizeof(qname),".beast-cleanup-quarantine-worker-%ld",(long)getpid());if(mkdirat(WORKSPACE_FD,qname,0700))return 96;int qfd=openat(WORKSPACE_FD,qname,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);if(qfd<0)return 96;
    int moved=0;for(int i=0;i<count;i++){if(validate_entry(&entries[i]))goto rollback;char base[512],target[32];int parent=open_parent(WORKSPACE_FD,entries[i].path,base);if(parent<0)goto rollback;snprintf(target,sizeof(target),"entry-%d",i);
        int ok=renameat(parent,base,qfd,target);close(parent);if(ok)goto rollback;moved++;}
    for(int i=0;i<count;i++){char target[32];snprintf(target,sizeof(target),"entry-%d",i);if(unlinkat(qfd,target,0))goto rollback;}close(qfd);if(unlinkat(WORKSPACE_FD,qname,AT_REMOVEDIR))return 97;
    printf("{\"beast_object_type\":\"isolated_worker_evidence\",\"version\":\"1.0\",\"manifest_digest\":\"%s\",\"files_removed\":%d,\"bytes_removed\":%llu,\"cleanup_verified\":true,\"namespace_inodes\":{\"mnt\":%lu,\"pid\":%lu,\"net\":%lu,\"user\":%lu},\"non_loopback_interface_count\":%d,\"private_proc_mounted\":true,\"filesystem_root_isolated\":true,\"secrets_denied\":true,\"isolated_loopback_service_verified\":%s,\"ambient_network_denied\":%s}\n",
        manifest_digest,count,total,ns_inode("mnt"),ns_inode("pid"),ns_inode("net"),ns_inode("user"),routes,loopback_fixture()?"true":"false",routes==0?"true":"false");fflush(stdout);return 0;
rollback:
    for(int i=moved-1;i>=0;i--){char target[32],base[512];snprintf(target,sizeof(target),"entry-%d",i);int parent=open_parent(WORKSPACE_FD,entries[i].path,base);if(parent>=0){(void)renameat(qfd,target,parent,base);close(parent);}}
    close(qfd);(void)unlinkat(WORKSPACE_FD,qname,AT_REMOVEDIR);return 98;
}

int main(int argc,char **argv){(void)argv;if(argc!=1)return 80;struct stat ws,mf;if(fstat(WORKSPACE_FD,&ws)||!S_ISDIR(ws.st_mode)||fstat(MANIFEST_FD,&mf)||!S_ISREG(mf.st_mode))return 81;
    uid_t uid=getuid();gid_t gid=getgid();if(unshare(CLONE_NEWUSER)||map_user(uid,gid)||unshare(CLONE_NEWNS|CLONE_NEWNET|CLONE_NEWPID)||mount(NULL,"/",NULL,MS_REC|MS_PRIVATE,NULL))return 82;
    int routes=non_loopback_interfaces();if(routes!=0)return 83;char root[128],proc[160];snprintf(root,sizeof(root),"/tmp/beast-disk-root-%ld",(long)getpid());snprintf(proc,sizeof(proc),"%s/proc",root);
    if(mkdir(root,0700)||mount("tmpfs",root,"tmpfs",MS_NOSUID|MS_NODEV|MS_NOEXEC,"size=16m")||mkdir(proc,0555))return 84;
    pid_t child=fork();if(child<0)return 85;if(child==0)_exit(cleanup_child(root,routes));int status=0;if(waitpid(child,&status,0)<0)return 86;
    int clean=umount2(proc,MNT_DETACH)==0;clean=umount2(root,MNT_DETACH)==0&&clean;clean=rmdir(root)==0&&clean;
    printf("{\"beast_object_type\":\"isolated_worker_cleanup\",\"root_cleanup_confirmed\":%s}\n",clean?"true":"false");fflush(stdout);
    if(!clean)return 87;
    return WIFEXITED(status)?WEXITSTATUS(status):88;}
