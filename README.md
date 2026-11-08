# Sound Open Firmware Topologies (`sof-topologies`)

Standalone repository containing the ALSA topology (`.tplg`) sources, build system, installation scripts, and inspection tooling for [Sound Open Firmware (SOF)](https://thesofproject.github.io/).

ALSA topology files describe the audio DSP graph (pipelines, widgets, routes, DAIs, controls) and are loaded dynamically by the Linux kernel SOF driver during initialization.

---

## Repository Structure

| Path | Description |
| :--- | :--- |
| [`topology1/`](topology1/README.md) | Legacy (v1) `m4`-based IPC3 topology sources (`i.MX8`, `i.MX8MP`, `i.MX8ULP`, `i.MX93`, `i.MX95`, `MediaTek MT8186/8188/8195/8196/8365`, `AMD ACP`, `CAVS nocodec`) |
| [`topology2/`](topology2/README.md) | Class-based (v2) `alsatplg -p` IPC4 & IPC3 topology sources (`Intel CAVS 2.5`, `ACE 1.x/2.x/3.x/4.x`, `HDA generic`, `SDCA generic`, `i.MX8`, `CHT`, and `sof-testbench4` development/benchmark graphs) |
| [`test/topology/`](test/topology/) | Automated component, SSP, and DMIC test topology matrix (`tplg-build.sh`) |
| [`include/kernel/abi.h`](include/kernel/abi.h) | Standalone SOF ABI version header used when generating topology manifests |
| [`tools/`](tools/) | Topology developer tools: [`tplgtool2.py`](tools/tplgtool2.py) (binary `.tplg` parser/graph dumper) and [`pretty-macro.sh`](tools/pretty-macro.sh) |
| [`scripts/`](scripts/) | Build (`build-topology.sh`), ALSA compiler setup (`build-alsa-tools.sh`), deployment (`install-topology.sh`), and `sof` synchronization (`sync-from-sof.sh`) scripts |

---

## Quick Start

### 1. Build Local `alsa-lib` and `alsa-utils` (`alsatplg` >= 1.2.7)
If you do not already have a recent `alsatplg` built in `../tools/bin/alsatplg`:
```bash
./scripts/build-topology.sh -A
```

### 2. Build Topologies
```bash
# Build all topology1 and topology2 production & development targets:
./scripts/build-topology.sh

# Or build specific subsets:
./scripts/build-topology.sh -1    # topology1 (M4 IPC3) only
./scripts/build-topology.sh -2    # topology2 (alsaconf v2 IPC4 & IPC3) only
./scripts/build-topology.sh -t    # test/topology matrix
./scripts/build-topology.sh -L    # also link outputs into ../sof/tools/build_tools/topology
```

Or directly with CMake + Ninja:
```bash
cmake -B build -GNinja
cmake --build build
```

### 3. Install Topologies
Using the helper script:
```bash
# Install locally into /lib/firmware/intel/{sof-tplg,sof-ipc4-tplg,sof-ace-tplg}:
sudo ./scripts/install-topology.sh

# Install into an offline/NFS rootfs:
./scripts/install-topology.sh --rootfs /srv/nfs/aphid-rootfs

# Deploy directly to a DUT over SSH:
./scripts/install-topology.sh --ssh root@aphid

# Populate versioned directories in a sof-bin release tree:
./scripts/install-topology.sh --sof-bin ../sof-bin/v2.14.x --version v2.14
```

Or using standard CMake install:
```bash
sudo cmake --install build --prefix /lib/firmware
```

### 4. Package Release Tarball
```bash
./scripts/build-topology.sh -p
# Generates build/sof-topology-<abi_version>.tar.gz
```

---

## Synchronizing with `sof` During CI Transition

While CI systems are transitioning from `sof/tools/topology` to `sof-topology`, use [`scripts/sync-from-sof.sh`](scripts/sync-from-sof.sh) to pull or push topology changes:
```bash
# Pull latest topology changes from ../sof into sof-topology:
./scripts/sync-from-sof.sh --pull

# Check whether sof-topology and ../sof are in sync (CI check):
./scripts/sync-from-sof.sh --check

# Push topology changes from sof-topology back to ../sof:
./scripts/sync-from-sof.sh --push
```
