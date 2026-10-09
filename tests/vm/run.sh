#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
test -f "$root/out/vm/Image"
test -f "$root/out/android16-6.12-ns/droidspaces_ns.ko"
vm_status=0
docker run --rm --platform linux/arm64 -v "$root:/work" \
    droidspaces-lkm-vm:local sh -eu -c '
    gcc -static -O2 -Wall -Wextra -Werror /work/tests/vm/load-module.c -o /tmp/load-module
    gcc -static -O2 -Wall -Wextra -Werror /work/tests/vm/namespaces.c -o /tmp/namespaces
    mkdir -p /tmp/root/bin /tmp/root/dev /tmp/root/proc /tmp/root/sys
    cp /usr/bin/busybox /tmp/root/bin/busybox
    for app in $(busybox --list); do
        test "$app" = busybox || ln -s busybox "/tmp/root/bin/$app"
    done
    cp /tmp/load-module /tmp/root/load-module
    cp /tmp/namespaces /tmp/root/namespaces
    cp /work/tests/vm/init /tmp/root/init
    chmod +x /tmp/root/init
    cp /work/out/android16-6.12-ns/droidspaces_ns.ko /tmp/root/
    mknod /tmp/root/dev/console c 5 1
    cd /tmp/root
    find . -print0 | cpio --null -o --format=newc > /tmp/initramfs
    timeout 180 qemu-system-aarch64 -machine virt -cpu max -m 2048 -smp 2 \
        -nographic -monitor none -nic none -no-reboot \
        -kernel /work/out/vm/Image -initrd /tmp/initramfs \
        -append "console=ttyAMA0 earlycon=pl011,0x9000000 rdinit=/init nokaslr selinux=0 panic=-1" \
        > /work/out/vm/console.log 2>&1
    ' || vm_status=$?
cat "$root/out/vm/console.log"
test "$vm_status" -eq 0
grep -q '^DS_VM_RESULT=0' "$root/out/vm/console.log"
if grep -Eq 'BUG:|WARNING:|Oops|Kernel panic' "$root/out/vm/console.log"; then
    echo 'Kernel diagnostics found in VM log' >&2
    exit 1
fi
