#!/usr/bin/env python3
"""Exercise real GMU OOB/HFI wait functions with a stalled fault-dump interleaving."""
import argparse
import os
from pathlib import Path
import re
import subprocess
import tempfile

PROJECT = Path(__file__).resolve().parents[1]
KERNEL = Path(os.environ.get('KERNEL_DIR', PROJECT / 'linux'))
FILES = ('drivers/gpu/drm/msm/adreno/a6xx_gmu.c',
         'drivers/gpu/drm/msm/adreno/a6xx_hfi.c')

STUBS = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <errno.h>
typedef uint32_t u32;
struct completion { bool done; };
struct msm_gpu { bool recovery_in_progress; };
struct adreno_gpu { struct msm_gpu base; struct completion fault_coredump_done; bool rgmu; };
struct a6xx_gmu { bool legacy; int lock; void *dev; };
struct a6xx_gpu { struct adreno_gpu base; struct a6xx_gmu gmu; };
static struct a6xx_gpu gpu;
enum a6xx_gmu_oob_state { GMU_OOB_GPU_SET, GMU_OOB_INVALID };
static const struct { const char *name; int set, ack, set_new, ack_new; }
a6xx_gmu_oob_bits[] = {{ "GPU_SET", 1, 2, 3, 4 }};
static const char *a6xx_hfi_msg_id[] = { "TEST" };
static int polls, waits, fails;
#define container_of(p,t,m) ((t *)((char *)(p) - offsetof(t,m)))
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define READ_ONCE(x) (x)
#define WARN_ON_ONCE(x) ((void)(x))
#define DRM_DEV_ERROR(dev,fmt,...) do { (void)(dev); if (0) printf(fmt, ##__VA_ARGS__); } while (0)
#define REG_A6XX_GMU_HOST2GMU_INTR_SET 1
#define REG_A6XX_GMU_GMU2HOST_INTR_INFO 2
#define REG_A6XX_GMU_GMU2HOST_INTR_CLR 3
#define A6XX_GMU_GMU2HOST_INTR_INFO_MSGQ 1
static bool mutex_is_locked(int *lock) { (void)lock; return true; }
static bool adreno_has_rgmu(struct adreno_gpu *adreno) { return adreno->rgmu; }
static bool completion_done(struct completion *c) { return c->done; }
static void wait_for_completion(struct completion *c) {
    waits++;
    /* The fault thread requires gpu->lock, held by the recovery worker.
     * Fail deterministically instead of hanging this host test forever. */
    if (gpu.base.base.recovery_in_progress) exit(90);
    c->done = true;
}
static int fake_poll(u32 *val) {
    polls++;
    *val = fails ? 0 : UINT32_MAX;
    if (fails) { fails--; return -ETIMEDOUT; }
    return 0;
}
#define gmu_poll_timeout(g,r,v,c,d,t) fake_poll(&(v))
static void gmu_write(struct a6xx_gmu *g, int r, u32 v) { (void)g; (void)r; (void)v; }
static u32 gmu_read(struct a6xx_gmu *g, int r) { (void)g; (void)r; return 0; }
'''

CASES = r'''
static void check(int (*waiter)(void), bool recovery, bool dump_done,
                  int failures, int expected, int expected_waits, int expected_polls) {
    gpu.base.base.recovery_in_progress = recovery;
    gpu.base.fault_coredump_done.done = dump_done;
    polls = waits = 0;
    fails = failures;
    assert(waiter() == expected);
    assert(waits == expected_waits);
    assert(polls == expected_polls);
}
static int oob(void) { return a6xx_gmu_set_oob(&gpu.gmu, GMU_OOB_GPU_SET); }
static int hfi(void) { return a6xx_hfi_wait_for_msg_interrupt(&gpu.gmu, 0, 1); }
int main(void) {
    int (*waiters[])(void) = { oob, hfi };
    for (unsigned i = 0; i < ARRAY_SIZE(waiters); i++) {
        check(waiters[i], false, true, 0, 0, 0, 1); /* normal acknowledgement */
        check(waiters[i], false, true, 1, -ETIMEDOUT, 0, 1); /* genuine timeout */
        check(waiters[i], false, false, 1, 0, 1, 2); /* dump completes, retry */
        check(waiters[i], true, false, 1, -ETIMEDOUT, 0, 1); /* recovery owns lock */
        check(waiters[i], true, false, 0, 0, 0, 1); /* recovery ack still works */
    }
    return 0;
}
'''


def check(ref=None):
    functions = []
    for path, name in zip(FILES, ('a6xx_gmu_set_oob', 'a6xx_hfi_wait_for_msg_interrupt')):
        source = (subprocess.check_output(['git', '-C', str(KERNEL), 'show', f'{ref}:{path}'], text=True)
                  if ref else (KERNEL / path).read_text())
        match = re.search(rf'^(?:static )?int {name}\(.*?^}}', source, re.M | re.S)
        if not match:
            raise RuntimeError(f'missing real driver function: {name}')
        functions.append(match[0])
    with tempfile.TemporaryDirectory(prefix='gpu-recovery-test-') as temp:
        source, binary = Path(temp) / 'wait.c', Path(temp) / 'wait'
        source.write_text(STUBS + '\n'.join(functions) + CASES)
        subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                        str(source), '-o', str(binary)], check=True)
        return subprocess.run([str(binary)], timeout=5).returncode


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', help='also demonstrate the unfixed kernel revision fails')
    args = parser.parse_args()
    if check() != 0:
        raise SystemExit('GMU wait recovery regression failed')
    if args.baseline and check(args.baseline) != 90:
        raise SystemExit('baseline did not reproduce the lock/completion deadlock')
    print('GMU OOB/HFI: ack, timeout, fault completion and recovery interleavings passed')
