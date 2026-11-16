CLANG ?= /usr/bin/clang
BPFTOOL ?= /usr/local/bin/bpftool
CC ?= cc
BUILD_DIR ?= build
BPF_ARCH ?= x86

BPF_OBJECT := $(BUILD_DIR)/beast_x1_observer.bpf.o
LOADER := $(BUILD_DIR)/libbeast_x2_loader.so
X3_BPF_OBJECT := $(BUILD_DIR)/beast_x3_redirect.bpf.o
X3_WORKER := $(BUILD_DIR)/beast_x3_af_xdp_worker
X6_BPF_OBJECT := $(BUILD_DIR)/beast_x6_admitted_fastpath.bpf.o
VMLINUX := $(BUILD_DIR)/vmlinux.h

.PHONY: all clean beast-x3-worker beast-x6-object
all: $(BPF_OBJECT) $(LOADER) $(X3_BPF_OBJECT) $(X3_WORKER)

beast-x3-worker: $(X3_BPF_OBJECT) $(X3_WORKER)

# Compile only; loading/attaching is an operator step (see app/kernel/networking/xdp_fastpath_sim.operator_commands).
beast-x6-object: $(X6_BPF_OBJECT)

$(BUILD_DIR):
	mkdir -p $@

$(VMLINUX): | $(BUILD_DIR)
	$(BPFTOOL) btf dump file /sys/kernel/btf/vmlinux format c > $@

$(BPF_OBJECT): beast_x1_observer.bpf.c $(VMLINUX)
	$(CLANG) -g -O2 -target bpf -D__TARGET_ARCH_$(BPF_ARCH) -I$(BUILD_DIR) -c $< -o $@

$(X3_BPF_OBJECT): beast_x3_redirect.bpf.c $(VMLINUX)
	$(CLANG) -g -O2 -target bpf -D__TARGET_ARCH_$(BPF_ARCH) -I$(BUILD_DIR) -c $< -o $@

$(X6_BPF_OBJECT): beast_x6_admitted_fastpath.bpf.c $(VMLINUX)
	$(CLANG) -g -O2 -target bpf -D__TARGET_ARCH_$(BPF_ARCH) -I$(BUILD_DIR) -c $< -o $@

$(LOADER): libbeast_x2_loader.c | $(BUILD_DIR)
	$(CC) -shared -fPIC -O2 -Wall -Wextra -Werror $< -o $@ $$(pkg-config --cflags --libs libbpf)

$(X3_WORKER): beast_x3_af_xdp_worker.c | $(BUILD_DIR)
	$(CC) -O2 -Wall -Wextra -Werror $< -o $@ $$(pkg-config --cflags --libs libbpf libxdp)

clean:
	rm -rf $(BUILD_DIR)
