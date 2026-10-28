Running Vortex on CHTC

These are the steps I use to build this repo and run kernels on UW-Madison's CHTC 
(learn.chtc.wisc.edu). At the end you get a log with Vortex's performance counters 
(cycles, IPC, stalls, instruction mix, etc.).

Note: The steps below run sgemm, the matrix-multiply kernel that ships with 
Vortex (tests/regression/sgemm)


Vortex's prebuilt toolchain (RISC-V compiler, Verilator, LLVM, etc.) only runs on Ubuntu, 
and CHTC machines aren't Ubuntu. So I built an Apptainer container: an Ubuntu 22.04 
image with the toolchain installed inside it at /opt/vortex-tools. You only build it once.

1. Clone the repo on learn
2. Build the container in a build job and save it to staging
3. Every time: start a job, enter the container, build Vortex, run kernels, exit

1. Clone the repo


ssh <netid>@learn.chtc.wisc.edu
cd ~
git clone --recursive https://github.com/AK17111/vortex_gpgpu_rtl.git
cd vortex_gpgpu_rtl
git checkout master        # or whichever branch you want to test
git submodule update --init --recursive
cd ~



--recursive pulls in the third_party/ submodules (cvfpu, softfloat, ramulator...). 
The build fails without them.


2. Build the container

Create the container recipe in your home folder:

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


What it does: starts from Ubuntu 22.04, installs the packages from 
ci/install_dependencies.sh, copies the repo in just long enough to run configure 
and toolchain_install.sh, then deletes the copy. The toolchain stays at 
/opt/vortex-tools. The chmod 1777 /tmp line is needed because /tmp isn't 
writable during the build otherwise, and apt-get fails.

Then the submit file for the build job:


cat > ~/build.sub <<'EOF'
executable = /usr/bin/hostname
transfer_input_files = image.def, vortex_gpgpu_rtl
+IsBuildJob = True
request_cpus = 8
request_memory = 16GB
request_disk = 60GB
queue
EOF


If a long paste comes out garbled in the terminal, check with cat image.def and 
cat build.sub. If either looks wrong, create it with nano instead.


Start the build job:

cd ~
condor_submit -i build.sub


When the prompt changes to a build... machine:

mkdir -p tmp && export APPTAINER_TMPDIR=$PWD/tmp
apptainer build vortex.sif image.def


This takes around 10 minutes and prints a lot. Wait for 
INFO: Build complete: vortex.sif before typing anything else, then:

mv vortex.sif /staging/${USER:0:1}/$USER/
exit


3. Submit file for work sessions

cat > ~/work.sub <<'EOF'
executable = /usr/bin/hostname
requirements = (HasCHTCStaging == true)
transfer_input_files = vortex_gpgpu_rtl
transfer_output_files = perf.log
request_cpus = 4
request_memory = 16GB
request_disk = 40GB
queue
EOF


- requirements asks for a machine that can see /staging, so the container doesn't 
- have to be copied into every job.
- transfer_input_files copies the repo into the job.
- transfer_output_files is the only file copied back when the job ends. It has to exist 
- when you exit, or the job goes on hold.

4. Build Vortex and run a kernel

Start a session:

cd ~
condor_submit -i work.sub


Once you're on the compute machine, enter the container:

apptainer shell -e /staging/${USER:0:1}/$USER/vortex.sif


The prompt changes to Apptainer>. Build Vortex, one line at a time:

TOP=$PWD
cd vortex_gpgpu_rtl && mkdir -p build && cd build
../configure --xlen=32 --tooldir=/opt/vortex-tools
make -s


TOP remembers the job's top folder, which is where perf.log has to end up. 
configure sets up the build folder and points it at the toolchain inside the container. 
make -s builds the runtime, the simulators, and the kernel libraries.

Run sgemm with performance counters on:

./ci/blackbox.sh --driver=simx --cores=1 --warps=4 --threads=4 --app=sgemm --perf=1 | tee $TOP/perf.log


You should see PASSED! and a block of PERF: lines. tee prints the output and saves 
it to perf.log at the same time.

5. Get the results

Leave the container, then end the job. That's two exits, and the prompt should end up 
back at [netid@learn ~]$:

exit
exit


HTCondor copies perf.log to your home folder on learn. To copy it to your laptop, 
run this in a terminal on your laptop (not logged in to CHTC):

scp <netid>@learn.chtc.wisc.edu:~/perf.log ~/Downloads/
grep -E "PERF|PASSED|vortex2:" ~/Downloads/perf.log


The grep filters out the build messages and leaves just the results.