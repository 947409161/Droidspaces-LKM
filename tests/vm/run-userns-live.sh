#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
log_dir=${DS_USERNS_LOG_DIR:-out/userns-live/vm}
case "$log_dir" in out/*) ;; *) exit 2;; esac
case "$log_dir" in *..*) exit 2;; esac
mkdir -p "$root/$log_dir"
status=0
docker run --rm --platform linux/arm64 -v "$root:/work" \
    -e KERNEL="${DS_USERNS_KERNEL:-/work/out/gki/android16-6.12/Image}" \
    -e MODULE="${DS_USERNS_MODULE:-/work/out/userns-live/droidspaces_ns.ko}" \
    -e SANDBOX="${DS_USERNS_SANDBOX:-0}" \
    -e LOG="/work/$log_dir/console.log" \
    droidspaces-lkm-vm:local sh -eu -c '
    gcc -static -O2 -Wall -Wextra -Werror /work/tests/vm/load-module.c -o /tmp/load-module
    gcc -static -O2 -Wall -Wextra -Werror /work/tests/vm/userns-live.c -o /tmp/userns-live-test
    gcc -static -pthread -O2 -Wall -Wextra -Werror /work/tests/vm/userns-policy.c -o /tmp/userns-policy-test
    mkdir -p /tmp/root/bin /tmp/root/dev /tmp/root/proc /tmp/root/sys /tmp/root/tmp
    chmod 1777 /tmp/root/tmp
    cp /usr/bin/busybox /tmp/root/bin/busybox
    for app in $(busybox --list); do test "$app" = busybox || ln -s busybox "/tmp/root/bin/$app"; done
    cp /tmp/load-module /tmp/root/load-module
    cp /tmp/userns-live-test /tmp/root/userns-live-test
    cp /tmp/userns-policy-test /tmp/root/userns-policy-test
    cp /tmp/userns-policy-test /tmp/root/userns-policy-suid-host
    chmod 4755 /tmp/root/userns-policy-suid-host
    cp /tmp/userns-policy-test /tmp/root/userns-policy-sgid-host
    chmod 2755 /tmp/root/userns-policy-sgid-host
    cp /tmp/userns-policy-test /tmp/root/userns-policy-suid-mapped
    chown 1000:1000 /tmp/root/userns-policy-suid-mapped
    chmod 4755 /tmp/root/userns-policy-suid-mapped
    mkdir -p /tmp/ext4-root /tmp/root/test-ext4
    cp /tmp/userns-policy-test /tmp/ext4-root/userns-policy-fcaps
    chown 1000:1000 /tmp/ext4-root/userns-policy-fcaps
    truncate -s 32M /tmp/root/filecaps.ext4
    mkfs.ext4 -q -F -d /tmp/ext4-root /tmp/root/filecaps.ext4
    mknod /tmp/root/dev/loop0 b 7 0
    mknod /tmp/root/dev/loop-control c 10 237
    if [ "$SANDBOX" != 0 ]; then
        cd /work/out/userns-live/sandbox-runtime/root
        sha256sum -c ../SHA256SUMS
        cd /
        cp -a /work/out/userns-live/sandbox-runtime/root/. /tmp/root/
        gcc -static -O2 -Wall -Wextra -Werror /work/tests/vm/userns-sandbox.c -o /tmp/root/sandbox-test
        if [ "$SANDBOX" = all ]; then touch /tmp/root/sandbox-all-enabled; fi
        touch /tmp/root/sandbox-enabled /tmp/root/host-should-be-hidden
        mkdir -p /tmp/root/tmp
        chmod 1777 /tmp/root/tmp
        mknod /tmp/root/dev/null c 1 3
        mknod /tmp/root/dev/zero c 1 5
        mknod /tmp/root/dev/full c 1 7
        mknod /tmp/root/dev/random c 1 8
        mknod /tmp/root/dev/urandom c 1 9
        mknod /tmp/root/dev/tty c 5 0
        chmod 666 /tmp/root/dev/null /tmp/root/dev/zero /tmp/root/dev/full /tmp/root/dev/random /tmp/root/dev/urandom /tmp/root/dev/tty
    fi
    cp "$MODULE" /tmp/root/namespaces.ko
    cp /work/tests/vm/userns-live-init /tmp/root/init
    chmod +x /tmp/root/init
    mknod /tmp/root/dev/console c 5 1
    cd /tmp/root
    find . -print0 | cpio --null -o --format=newc > /tmp/initramfs
    timeout 180 qemu-system-aarch64 -machine virt -cpu max -m 2048 -smp 2 \
        -nographic -monitor none -nic none -no-reboot -kernel "$KERNEL" -initrd /tmp/initramfs \
        -append "console=ttyAMA0 earlycon=pl011,0x9000000 rdinit=/init nokaslr selinux=0 panic=-1" \
        > "$LOG" 2>&1
    ' || status=$?
tail -n 65 "$root/$log_dir/console.log"
test "$status" = 0
grep -q '^DS_USERNS_LIVE_VM_RESULT=0' "$root/$log_dir/console.log"
grep -q 'DS_USERNS_POLICY_PASS:' "$root/$log_dir/console.log"
grep -q 'DS_USERNS_LIVE_PASS:' "$root/$log_dir/console.log"
! grep -Eq 'BUG:|WARNING:|Oops|Kernel panic' "$root/$log_dir/console.log"
if [ "${DS_USERNS_SANDBOX:-0}" != 0 ]; then
    grep -q 'DS_USERNS_SANDBOX_PASS:' "$root/$log_dir/console.log"
fi
if [ "${DS_USERNS_SANDBOX:-0}" = all ]; then
    grep -q 'DS_USERNS_SANDBOX_DISABLED_PASS:' "$root/$log_dir/console.log"
    grep -q 'DS_USERNS_SANDBOX_ALL_PASS:' "$root/$log_dir/console.log"
fi
