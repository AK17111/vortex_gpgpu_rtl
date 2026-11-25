# Running Vortex on CHTC

These are the steps I use to build this repo and run kernels on CHTC
(learn.chtc.wisc.edu). Plain performance runs use simx, and the clock gating runs and
waveforms use rtlsim. 

Vortex's prebuilt toolchain only runs on Ubuntu and CHTC machines aren't Ubuntu, so
everything runs inside an Apptainer container: an Ubuntu 22.04 image with the toolchain
installed at /opt/vortex-tools. You build the container once, and after that each session
is: start a job, enter the container, build Vortex, run kernels, exit.


## 1. Clone the repo


```bash
ssh <netid>@learn.chtc.wisc.edu
cd ~
git clone --recursive https://github.com/AK17111/vortex_gpgpu_rtl.git
cd vortex_gpgpu_rtl
git checkout test_clkgate     # or master for the original Vortex
git submodule update --init --recursive
cd ~
```


## 2. Build the container (once)

Skip this if your staging folder already has vortex.sif (`ls /staging/${USER:0:1}/$USER/`).

 in your home folder:

```bash
cat > ~/image.def <<'EOF'
Bootstrap: docker
From: ubuntu:22.04

%files
    vortex_gpgpu_rtl /opt/vortex-src

%post
    mkdir -p /tmp && chmod 1777 /tmp
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -y
    apt-get install -y build-essential valgrind libstdc++6 binutils python3 \
        uuid-dev ccache cmake libffi8 libpng-dev libboost-serialization-dev \
        opencl-headers ocl-icd-opencl-dev git wget curl ca-certificates xz-utils bzip2 file
    apt-get clean
    git config --system --add safe.directory '*'
    cd /opt/vortex-src && mkdir -p build-tc && cd build-tc
    ../configure --xlen=32 --tooldir=/opt/vortex-tools
    ./ci/toolchain_install.sh
    cd / && rm -rf /opt/vortex-src
EOF
```


The submit file for the build job:

```bash
cat > ~/build.sub <<'EOF'
executable = /usr/bin/hostname
transfer_input_files = image.def, vortex_gpgpu_rtl
+IsBuildJob = True
request_cpus = 8
request_memory = 16GB
request_disk = 60GB
queue
EOF
```



Start the build job:

```bash
cd ~
condor_submit -i build.sub
```

When the prompt changes to a build machine:

```bash
mkdir -p tmp && export APPTAINER_TMPDIR=$PWD/tmp
apptainer build vortex.sif image.def
```

It takes about 10 minutes. Wait for `INFO: Build complete: vortex.sif` before typing
anything else, then:

```bash
mv vortex.sif /staging/${USER:0:1}/$USER/
exit
```

## 3. Submit file for work sessions (once)

```bash
cat > ~/work.sub <<'EOF'
executable = /usr/bin/hostname
requirements = (HasCHTCStaging == true)
transfer_input_files = vortex_gpgpu_rtl
transfer_output_files = results.tar.gz
request_cpus = 4
request_memory = 16GB
request_disk = 40GB
queue
EOF
```

The requirements line asks for a machine that can see /staging, so the container doesn't
get copied into every job. Only results.tar.gz comes back when the job ends, so
everything you want to keep goes into it. It has to exist when you exit or the job goes
on hold (`condor_rm <job id>` clears it).

## 4. Start a session

On learn, get the latest code and start a job:

```bash
cd ~/vortex_gpgpu_rtl
git fetch && git checkout test_clkgate && git pull
git submodule update --init --recursive
cd ~
condor_submit -i work.sub
```

It can sit at "Waiting for job to start..." for a few minutes. Once you're on the compute
machine, enter the container. Run this line by itself and wait for the `Apptainer>`
prompt before pasting anything else, because lines pasted together with it get dropped:

```bash
apptainer shell -e /staging/${USER:0:1}/$USER/vortex.sif
```

Then build:

```bash
TOP=$PWD
echo $TOP
cd vortex_gpgpu_rtl && mkdir -p build && cd build
../configure --xlen=32 --tooldir=/opt/vortex-tools
make -s
mkdir -p $TOP/out
```

TOP is the job's top folder. It has to be set after `apptainer shell` since `-e` starts
with a clean environment, and `echo $TOP` should print a path ending in /scratch. make
takes 10-20 minutes. Anything you want back goes in $TOP/out.

## 5. Performance counters (simx)

simx is Vortex's C++ model. It's fast and prints the performance counters, but it doesn't
use the Verilog, so it won't show any clock gating.

```bash
./ci/blackbox.sh --driver=simx --cores=1 --warps=4 --threads=4 --app=sgemm --perf=1 | tee $TOP/out/sgemm_simx.log
```

You should see `PASSED!` and a block of `PERF:` lines. Swap sgemm for softmax, vecadd,
diverge and so on.

## 6. Clock gating (rtlsim)

rtlsim runs the actual Verilog through Verilator. The clock gates are off unless you turn
them on with CONFIGS in front of the command:

```
(nothing)                    no gating, baseline
CONFIGS="-DVX_ICG_ENABLE"    all gates
CONFIGS="-DVX_ICG_ALU_INT"   integer ALU only
CONFIGS="-DVX_ICG_MULDIV"    multiply/divide only
CONFIGS="-DVX_ICG_FPU"       FPU only
CONFIGS="-DVX_ICG_SFU"       SFU warp control only
```

You can combine them, e.g. `CONFIGS="-DVX_ICG_FPU -DVX_ICG_MULDIV"`. The rtlsim model
rebuilds itself when the flags change.

First check that gating doesn't change anything. Run the same kernel without and with it:

```bash
./ci/blackbox.sh --driver=rtlsim --cores=1 --warps=4 --threads=4 --app=sgemm --args="-n16" --perf=1 | tee $TOP/out/sgemm_base.log
CONFIGS="-DVX_ICG_ENABLE" ./ci/blackbox.sh --driver=rtlsim --cores=1 --warps=4 --threads=4 --app=sgemm --args="-n16" --perf=1 | tee $TOP/out/sgemm_icg.log
grep -H "PASSED\|PERF: instrs" $TOP/out/sgemm_*.log
```

Both should pass with the same cycle count (18,621 for this setup). Gating saves power,
not time, so different cycles means a gate is broken.

To record waveforms, add `--vcd`, which writes trace.vcd. Keep it small; sgemm with -n8 is
about 40 MB per trace:

```bash
./ci/blackbox.sh --driver=rtlsim --cores=1 --warps=4 --threads=4 --app=sgemm --args="-n8" --vcd
mv trace.vcd $TOP/out/sgemm_base.vcd

CONFIGS="-DVX_ICG_ENABLE" ./ci/blackbox.sh --driver=rtlsim --cores=1 --warps=4 --threads=4 --app=sgemm --args="-n8" --vcd
mv trace.vcd $TOP/out/sgemm_icg.vcd
```

For longer kernels you can record just a slice. The trace timestamp counts twice per
clock cycle, so cycles 50,000 to 60,000 are 100000 to 120000:

```bash
CONFIGS="-DVX_ICG_ENABLE -DTRACE_START_TIME=100000ull -DTRACE_STOP_TIME=120000ull" \
  ./ci/blackbox.sh --driver=rtlsim --cores=1 --warps=4 --threads=4 --app=softmax --args="-n8" --vcd
mv trace.vcd $TOP/out/softmax_icg.vcd
```

The scripts in icg_tools/ are optional. They read a gated trace and print how often each
unit's clock was off and how long the idle stretches were:

```bash
python3 ../icg_tools/idle_windows.py $TOP/out/sgemm_icg.vcd | tee $TOP/out/idle_sgemm.txt
python3 ../icg_tools/lead_time.py   $TOP/out/sgemm_icg.vcd | tee $TOP/out/lead_sgemm.txt
```

## 7. Pack, exit, download

```bash
cd $TOP && tar czf results.tar.gz out
ls -lh results.tar.gz
exit
exit
```

One exit leaves the container and the second ends the job. You should be back at the
learn prompt. Then in a terminal on your laptop, not the one logged in to CHTC:

```bash
scp <netid>@learn.chtc.wisc.edu:~/results.tar.gz ~/Downloads/
cd ~/Downloads && tar xzf results.tar.gz
grep -E "PERF|PASSED" out/*.log
```

## 8. Looking at the waveforms

I use Surfer (`brew install surfer` on a Mac). Open both traces:

```bash
surfer ~/Downloads/out/sgemm_icg.vcd &
surfer ~/Downloads/out/sgemm_base.vcd &
```

The waveform area starts empty. In the hierarchy on the left (B toggles it), open the
arrows down to

```
TOP > rtlsim_shim > vortex > g_clusters[0] > cluster > g_sockets[0] > socket > g_cores[0] > core > execute
```

Click a scope name to list its signals underneath, then click a signal to add it. For
the FPU, add `clk` from fpu_unit > g_blocks[0] > fpu_dpi (it's in both traces), and
`clk_en` and `inflight` from fpu_unit > g_blocks[0] > fpu_icg (gated trace only). The
other units are the same idea: alu_int and int_icg, muldiv_unit and mdv_icg under
alu_unit > g_blocks[0], and wctl_unit and wctl_icg under sfu_unit.

Shift+F fits the whole run, + and - zoom. In the gated trace the FPU clock only toggles
while clk_en is high. In the baseline it toggles the whole time, and those extra edges
are what the gate saves. Cmd+S saves your signal list so you don't have to set it up
again.

## Things that went wrong for me

- `mkdir: cannot create directory '/out'`: TOP was empty. Set `TOP=$PWD` after
  `apptainer shell`, or from inside the repo use `TOP=${PWD%%/vortex_gpgpu_rtl*}`.
- Nothing after `apptainer shell` ran: I'd pasted it together with the next lines.
- rtlsim build stopping with EOFNEWLINE: a .sv file was missing the newline at the end.
  `printf '\n' >> <file>` fixes it.
- Job on hold after exit: results.tar.gz didn't exist. `condor_rm <job id>` and redo it.
- `scp ... No such file`: I'd run scp on learn instead of my laptop.
- A gating flag that seemed to do nothing: the run was on simx. Gating needs rtlsim.