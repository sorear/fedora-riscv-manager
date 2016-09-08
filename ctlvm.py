#!/bin/python3
import sys
import subprocess
import os
import datetime

def installdeps():
    subprocess.run('dnf copr enable rjones/riscv', shell=True, check=True)
    subprocess.run('dnf install git riscv-qemu riscv-pk', shell=True, check=True)

def safemount(dir, file):
    try:
        os.unlink(dir + '/mountimg')
    except:
        pass
    subprocess.run(['cp', '--reflink', dir + '/' + file, dir + '/mountimg'], check=True)
    os.makedirs(dir + '/mountdir', exist_ok=True)
    subprocess.run(['sudo', 'mount', '-o', 'loop', dir + '/mountimg', dir + '/mountdir'], check=True)

def safeumount(dir, file):
    subprocess.run(['sudo', 'umount', dir + '/mountdir'], check=True)
    subprocess.run(['cp', '--reflink', dir + '/mountimg', dir + '/' + file], check=True)

def inspect(dir):
    safemount(dir, 'rootfs')
    subprocess.run(['bash'], cwd=dir + '/mountdir')
    safeumount(dir, 'rootfs')

def injectinit(dir, text):
    subprocess.run(['cp', '--reflink', dir + '/rootfs', dir + '/scratch'], check=True)
    safemount(dir, 'scratch')
    with open(dir + '/mountdir/init', 'w') as init:
        uxtime = datetime.datetime.now().isoformat()
        columns, lines = os.get_terminal_size()
        init.write("#!/bin/bash\n")
        init.write("date --set " + uxtime + "; export LINES=" + str(lines) + "; export COLUMNS=" + str(columns) + "\n")
        init.write("""
PS4='stage3$ '
mount.static -o remount,rw /
mount.static -t proc /proc /proc
mount.static -t sysfs /sys /sys
mount.static -t tmpfs -o "nosuid,size=20%,mode=0755" tmpfs /run
mkdir -p /dev/pts
mount.static -t devpts devpts /dev/pts
mkdir -p /run/lock
ldconfig /usr/lib64 /usr/lib /lib64 /lib
hostname stage3
echo stage3.fedoraproject.org > /etc/hostname

# Set up the PATH.  The GCC path is a hack because I wasn't able to
# find the right flags for configuring GCC.
PATH=/usr/libexec/gcc/riscv64-unknown-linux-gnu/6.1.0:\
/usr/local/bin:\
/usr/local/sbin:\
/usr/bin:\
/usr/sbin:\
/bin:\
/sbin
export PATH
PS1='stage3:\w\$ '
export PS1
set -x
""")
        init.write(text + "\n")
        init.write("""
set +x
sync
while ! mount.static -n -o remount,ro /; do
    ps -elf
    sleep 2
    kill -- -1
    sleep 2
    kill -9 -- -1
done
sync
echo This message indicates that the VM shut down correctly.
poweroff
""")
    safeumount(dir, 'scratch')

def runqemu(dir, timeout, no_input):
    input = None
    if no_input:
        input = subprocess.PIPE
    with subprocess.Popen(['script','-a','-c','timeout -s9 ' + str(timeout) + ' qemu-system-riscv -m 2G -kernel /usr/bin/bbl -append vmlinux -drive file=scratch,format=raw -nographic','lastlog'], cwd=dir, stdin=input) as p:
        p.wait()
    with open(dir + '/lastlog', 'r') as f:
        log = f.read()
    if 'This message indicates that the VM shut down correctly' in log:
        subprocess.run(['cp', '--reflink', dir + '/scratch', dir + '/rootfs'], check=True)
    else:
        raise Exception("VM did not shut down cleanly")

def interact(dir):
    injectinit(dir, "bash")
    runqemu(dir, 9999999, False)

def runshort(dir, timeout, cmd):
    injectinit(dir, cmd)
    runqemu(dir, timeout, True)

def autobuild(dir, srpm):
    safemount(dir, 'rootfs')
    subprocess.run(['sudo', 'cp', srpm, dir + '/mountdir/input.srpm'])
    safeumount(dir, 'rootfs')
    runshort(dir, 99999, 'rm -rf /rpmbuild && rpm -i /input.srpm && script -c "rpmbuild -ba --define \\"debug_package %{nil}\\" --nodeps /rpmbuild/SPECS/*.spec"')
    getrpms(dir)

def autobuild_edit(dir):
    runshort(dir, 99999, 'rpmbuild -ba --define "debug_package %{nil}" --nodeps /rpmbuild/SPECS/*.spec')
    getrpms(dir)

def getrpms(dir):
    safemount(dir, 'rootfs')
    subprocess.run(['sudo', 'sh', '-c', 'cp '+dir+'/mountdir/rpmbuild/RPMS/*/* '+dir+'/mountdir/rpmbuild/SRPMS/* '+dir])
    safeumount(dir, 'rootfs')

def injectrpm(dir, *rpmglob):
    safemount(dir, 'rootfs')
    subprocess.run(['sudo', 'sh', '-c', 'cp '+' '.join(rpmglob)+' '+dir+'/mountdir/tmp/'])
    safeumount(dir, 'rootfs')
    runshort(dir, 99999, '(set +x; for x in $(rpm -qa); do rm -f /tmp/$x.rpm; done); rpm -Uvh --nodeps /tmp/*.rpm && rm /tmp/*.rpm')

if __name__ == "__main__":
    globals()[sys.argv[1]](*sys.argv[2:])
