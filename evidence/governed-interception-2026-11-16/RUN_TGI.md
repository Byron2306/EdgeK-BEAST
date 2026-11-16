# Local GPU serving on the RTX 3050 6 GB: TGI / time-share (commands for Byron)

All facts checked 2026-11-16 with nvidia-smi / docker info / free:
- **GPU:** RTX 3050 6 GB Laptop, driver 620.70.06, CUDA 13.5.
- **VRAM:** ComfyUI (pid 746277) holds **4134 MiB**.
- **RAM:** 14.8 GiB, ~1-4.5 GB available while ComfyUI is resident (RSS 7.9 GB).
- **Docker 29.9.3:** runtimes are runc only. **No nvidia-container-toolkit, no CDI spec.**
- **Disk:** `/` 6 GB free after the qwen2.5-coder:7b pull; `/data` 4.2 GB free.

TGI cannot offload layers to the CPU. Whatever it serves (weights + KV + CUDA graphs) must fit in free VRAM. On this laptop, **Ollama/llama.cpp is the better default** because of hybrid offload. TGI is worth it only for continuous batching of parallel agent calls with a small model when the GPU is otherwise idle.

## 0. Free the GPU first (pick one)
```bash
# a) stop ComfyUI when not generating images (frees ~4.1 GB VRAM and ~7.9 GB RAM)
kill -TERM 746277            # or close it from the Lilith/Tauri UI
# b) unload any Ollama model (the daemon stays up)
curl -s localhost:11434/api/generate -d '{"model":"qwen3:4b","keep_alive":0}'
nvidia-smi --query-gpu=memory.used,memory.total --format=csv
```

## 1. GPU access for Docker (sudo, one-time). CDI route, no docker daemon restart
Docker 29 already scans `/etc/cdi`. A daemon restart would also restart seraph and the Commons containers, so avoid `nvidia-ctk runtime configure && systemctl restart docker` unless you plan for that.
```bash
# Debian/Ubuntu: NVIDIA's apt repo per https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html
sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk cdi generate --output=/etc/cdi/nvidia.yaml
nvidia-ctk cdi list            # expect nvidia.com/gpu=0 and nvidia.com/gpu=all
docker run --rm --device nvidia.com/gpu=all ubuntu nvidia-smi
```

## 2. TGI sized for 6 GB
The image is ~10 GB on `/`, which has 6 GB free, so free disk first or move Docker's data-root. (Keep qwen2.5-coder:7b: at full GPU it is now the fastest local coder, see PHASE_A §6.)
The HF token goes in by **env-var name only**. Docker reads it from your shell environment, and the value never appears in the command line or `ps`:
```bash
export HF_TOKEN="$(cat ~/.cache/huggingface/token)"   # not echoed
chmod 600 ~/.cache/huggingface/token                  # currently 664
docker run -d --name beast-tgi --device nvidia.com/gpu=all --shm-size 1g \
  -p 127.0.0.1:8090:80 -v /data/byron/hf-cache:/data -e HF_TOKEN \
  ghcr.io/huggingface/text-generation-inference:latest \
  --model-id Qwen/Qwen2.5-Coder-3B-Instruct-AWQ --quantize awq \
  --max-input-tokens 3072 --max-total-tokens 4096 --max-batch-prefill-tokens 3072 \
  --max-concurrent-requests 8 --cuda-memory-fraction 0.85
unset HF_TOKEN
curl -s 127.0.0.1:8090/health && curl -s 127.0.0.1:8090/info | head -c 400
```

Sizing notes:
- **Qwen2.5-Coder-3B AWQ:** about 2.0 GB weights. KV for Qwen2.5-3B (36 layers, 2 KV heads × 128 dim, fp16) is about 36 KiB/token, so 4096 tokens × 8 concurrent ≈ 1.2 GB, plus CUDA graphs and buffers ≈ 0.6 GB. That gives **~4 GB at peak**, which fits only with ComfyUI stopped.
- **Qwen2.5-Coder-7B-Instruct-AWQ:** about 5.2 GB weights. Only possible with the whole GPU free, `--max-total-tokens 2048 --max-concurrent-requests 2`, no CUDA graphs (`--cuda-graphs 0`), and still borderline. Use the 7B through Ollama hybrid offload instead (numbers in PHASE_A §6).
- **Qwen2.5-Coder-1.5B-Instruct in fp16:** about 3.1 GB. Works, but quality is lower than 3B AWQ.
- BEAST wiring: `export TGI_BASE_URL=http://127.0.0.1:8090`. `governed_client.default_candidates()` then adds a `tgi` candidate (OpenAI Messages API, `response_format: {type: json_object, value: <schema>}` grammar).
- vLLM, as an alternative to TGI: `vllm/vllm-openai` with `--gpu-memory-utilization 0.8 --max-model-len 4096` behaves the same and has guided_json. The same CDI step is needed.

## 3. Ollama vs TGI time-share (recommended policy)
- **Default:** Ollama owns the GPU. On-demand loading, hybrid offload, and models unload after keep_alive.
- **TGI window:** only when ComfyUI is stopped and a batch of parallel agent calls is queued. First unload Ollama models (`keep_alive:0`), then start TGI. Stop TGI (`docker stop beast-tgi`) when the batch drains.
- BEAST's placement planner reads live free VRAM and RAM before each local call and routes to cloud rather than swap-thrash. With BEAST_PROCESS_LIFECYCLE, BEAST can tear down serving processes **it spawned** (pidfd + cgroup.kill). It never touches the system Ollama daemon (unload only), ComfyUI, or containers it didn't start.

## 4. Optional Ollama server tuning (sudo, systemd drop-in)
```bash
sudo systemctl edit ollama   # add:
# [Service]
# Environment="OLLAMA_FLASH_ATTENTION=1"
# Environment="OLLAMA_KV_CACHE_TYPE=q8_0"     # halves KV memory; q4_0 quarters it (some quality loss)
# Environment="OLLAMA_MAX_LOADED_MODELS=1"
sudo systemctl restart ollama
```
MoE expert offload (`--n-cpu-moe N` / `-ot exps=CPU`) is a llama.cpp `llama-server` flag. Ollama does not expose it per request, so it needs a BEAST-spawned llama-server, like the lifecycle demo uses.
