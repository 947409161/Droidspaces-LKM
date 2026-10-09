// SPDX-License-Identifier: GPL-2.0-only
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <sched.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mount.h>
#include <sys/msg.h>
#include <sys/sem.h>
#include <sys/shm.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

#define CHECK(expr) do { if (!(expr)) { \
	dprintf(2, "FAIL line %d: %s (errno=%d)\n", __LINE__, #expr, errno); \
	_exit(1); } } while (0)

static void reap(pid_t child)
{
	int status;
	CHECK(waitpid(child, &status, 0) == child);
	CHECK(WIFEXITED(status) && WEXITSTATUS(status) == 0);
}

static void leave_orphan(void)
{
	pid_t child = fork();
	CHECK(child >= 0);
	if (!child) {
		for (;;)
			pause();
	}
}

static void container_init(void)
{
	char self[32];
	pid_t child;
	ssize_t len;

	CHECK(getpid() == 1);
	CHECK(getppid() == 0);
	CHECK(unshare(CLONE_NEWNS) == 0);
	CHECK(mount(NULL, "/", NULL, MS_REC | MS_PRIVATE, NULL) == 0);
	CHECK(mount("proc", "/proc", "proc", 0, NULL) == 0);
	len = readlink("/proc/self", self, sizeof(self) - 1);
	CHECK(len > 0);
	self[len] = 0;
	CHECK(strcmp(self, "1") == 0);
	child = fork();
	CHECK(child >= 0);
	if (!child) {
		CHECK(getpid() == 2);
		CHECK(unshare(CLONE_NEWPID | CLONE_NEWIPC) == 0);
		pid_t nested = fork();
		CHECK(nested >= 0);
		if (!nested) {
			CHECK(getpid() == 1);
			CHECK(getppid() == 0);
			leave_orphan();
			_exit(0);
		}
		reap(nested);
		_exit(0);
	}
	reap(child);
	leave_orphan();
	_exit(0);
}

static int clone_init(void *unused)
{
	(void)unused;
	container_init();
	return 1;
}

int main(void)
{
	struct stat initial, isolated, restored;
	int ipc_fd = open("/proc/self/ns/ipc", O_RDONLY | O_CLOEXEC);
	int pid_fd = open("/proc/self/ns/pid", O_RDONLY | O_CLOEXEC);
	CHECK(ipc_fd >= 0 && pid_fd >= 0);
	CHECK(fstat(ipc_fd, &initial) == 0);
	for (int i = 0; i < 8; i++) {
		CHECK(unshare(CLONE_NEWIPC | CLONE_NEWPID) == 0);
		CHECK(stat("/proc/self/ns/ipc", &isolated) == 0);
		CHECK(isolated.st_ino != initial.st_ino);
		pid_t child = fork();
		CHECK(child >= 0);
		if (!child)
			container_init();
		reap(child);
		CHECK(setns(ipc_fd, CLONE_NEWIPC) == 0);
		CHECK(setns(pid_fd, CLONE_NEWPID) == 0);
		CHECK(stat("/proc/self/ns/ipc", &restored) == 0);
		CHECK(restored.st_ino == initial.st_ino);
	}
	void *stack = malloc(65536);
	CHECK(stack != NULL);
	pid_t child = clone(clone_init, (char *)stack + 65536,
			    CLONE_NEWPID | CLONE_NEWIPC | SIGCHLD, NULL);
	CHECK(child >= 0);
	reap(child);
	free(stack);
	child = fork();
	CHECK(child >= 0);
	if (!child) {
		CHECK(setuid(65534) == 0);
		errno = 0;
		CHECK(setns(ipc_fd, CLONE_NEWIPC) == -1 && errno == EPERM);
		errno = 0;
		CHECK(unshare(CLONE_NEWPID) == -1 && errno == EPERM);
		_exit(0);
	}
	reap(child);
	CHECK(close(ipc_fd) == 0);
	CHECK(close(pid_fd) == 0);
	/* Identity/lifetime support must not be reported as working SysV IPC. */
	errno = 0;
	CHECK(msgget(IPC_PRIVATE, 0600) == -1 && errno == ENOSYS);
	errno = 0;
	CHECK(semget(IPC_PRIVATE, 1, 0600) == -1 && errno == ENOSYS);
	errno = 0;
	CHECK(shmget(IPC_PRIVATE, 4096, 0600) == -1 && errno == ENOSYS);
	puts("DS_IPC_BACKENDS_ABSENT: msgget/semget/shmget still return ENOSYS");
	puts("DS_NAMESPACES_PASS: PID 1, nested PID, procfs, orphan reaping, IPC identity, setns, clone, permissions");
	return 0;
}
