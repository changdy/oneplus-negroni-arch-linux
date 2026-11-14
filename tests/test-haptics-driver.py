#!/usr/bin/env python3
"""Compile the real haptics FF callbacks and check desktop playback regressions."""
from pathlib import Path
import os
import re
import subprocess
import sys
import tempfile


def function(source, name):
    match = re.search(r'static (?:int|void) ' + re.escape(name) + r'\(', source)
    if not match:
        raise RuntimeError(f'Missing callback: {name}')
    start = match.start()
    end = source.index('{', start) + 1
    depth = 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


MOCKS = r'''
#include <assert.h>
#include <errno.h>
#include <linux/input.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef int16_t s16;
typedef int atomic_t;
struct work_struct { bool pending; };
struct delayed_work { struct work_struct work; unsigned delay; };
struct mutex { bool held; };
struct brake_cfg {};
struct input_dev;
struct haptics_hw_config { bool measure_lra_impedance; unsigned vmax_mv; };
struct haptics_effect { unsigned vmax_mv; };
struct haptics_play_info {
    struct mutex lock;
    atomic_t gain;
    unsigned pattern_src, vmax_mv;
    struct haptics_effect *effect;
};
struct haptics_chip {
    void *dev;
    struct haptics_play_info play;
    struct haptics_hw_config config;
    struct work_struct play_work, set_gain_work;
    struct delayed_work stop_work;
    atomic_t play_requested;
    unsigned direct_length_ms, wa_flags;
    u8 direct_amplitude;
    bool visense_enabled, clamp_at_5v;
    unsigned pattern_start_time;
};
#define DIRECT_PLAY 1
#define SRC_INVALID 9
#define FIFO 0
#define IGNORE_SWR_IN_SPMI_PLAY 256
#define CLAMPED_VMAX_MV 5000
#define CUSTOM_DATA_LEN 3
struct custom_fifo_data { char data[20]; };
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
#define min(a,b) ((a)<(b)?(a):(b))
#define max(a,b) ((a)>(b)?(a):(b))
#define atomic_read(a) (*(a))
#define atomic_set(a,v) (*(a)=(v))
#define input_get_drvdata(d) (test_chip)
#define msecs_to_jiffies(v) (v)
#define dev_dbg(...) ((void)0)
#define dev_err(...) ((void)0)
#define system_wq NULL
static struct haptics_chip *test_chip;
static bool playing, powered;
static unsigned starts, stops, io_count, amplitude, load_count;
static int load_error, boost_error, pm_puts;
static void mutex_lock(struct mutex *m) { assert(!m->held); m->held=true; }
static void mutex_unlock(struct mutex *m) { assert(m->held); m->held=false; }
static void cancel_work_sync(struct work_struct *w) { assert(!test_chip->play.lock.held); w->pending=false; }
static void cancel_delayed_work_sync(struct delayed_work *w) { assert(!test_chip->play.lock.held); w->work.pending=false; }
static void schedule_work(struct work_struct *w) { w->pending=true; }
static void schedule_delayed_work(struct delayed_work *w,unsigned delay) { w->work.pending=true; w->delay=delay; }
static void mod_delayed_work(void *q,struct delayed_work *w,unsigned delay) { schedule_delayed_work(w,delay); }
static int haptics_enable_play(struct haptics_chip *c,bool on) { io_count++; playing=on; if(on) starts++; else stops++; return 0; }
static int haptics_enable_hpwr_vreg(struct haptics_chip *c,bool on) { io_count++; powered=on; return 0; }
/* The real helper checks SWR state under play.lock. Preserve that locking. */
static int haptics_wait_hboost_ready(struct haptics_chip *c) { mutex_lock(&c->play.lock); mutex_unlock(&c->play.lock); return boost_error; }
static int haptics_runtime_resume_get(struct haptics_chip *c) { return 0; }
static void haptics_runtime_autosuspend_put(struct haptics_chip *c) { pm_puts++; }
static int haptics_ignore_swr_play(struct haptics_chip *c,bool on) { return 0; }
static unsigned get_direct_play_max_amplitude(struct haptics_chip *c) { return 255; }
static int haptics_load_constant_effect(struct haptics_chip *c,u8 v) { load_count++; amplitude=v; c->play.pattern_src=DIRECT_PLAY; return load_error; }
static int haptics_load_custom_effect(struct haptics_chip *c,void *d,unsigned n,int v) { return 0; }
static int haptics_load_periodic_effect(struct haptics_chip *c,void *d,unsigned n,int v) { return 0; }
static void haptics_stop_fifo_play(struct haptics_chip *c) {}
static void haptics_set_fifo_empty_threshold(struct haptics_chip *c,unsigned v) {}
static unsigned ktime_get_boottime(void) { return 123; }
static int haptics_set_direct_play(struct haptics_chip *c,u8 v) { amplitude=v; return 0; }
static int haptics_set_vmax_mv(struct haptics_chip *c,unsigned v) { return 0; }
'''

TESTS = r'''
static void run_play(struct haptics_chip *c) {
    assert(c->play_work.pending); c->play_work.pending=false;
    haptics_play_work(&c->play_work);
}
static void expire(struct haptics_chip *c) {
    assert(c->stop_work.work.pending); c->stop_work.work.pending=false;
    haptics_stop_constant_effect_play(&c->stop_work.work);
}
int main(void) {
    struct haptics_chip c={0};
    struct input_dev *dev=NULL;
    struct ff_effect e={0};
    test_chip=&c; c.play.pattern_src=SRC_INVALID; c.play.gain=65535;
    e.type=FF_CONSTANT; e.u.constant.level=32767; e.replay.length=80;
    assert(haptics_upload_effect(dev,&e,NULL)==0);
    assert(amplitude==255 && !playing && !c.stop_work.work.pending);
    unsigned before=io_count;
    haptics_playback(dev,0,1);
    assert(io_count==before); /* No potentially sleeping I/O under event_lock. */
    run_play(&c);
    assert(playing && powered && c.stop_work.work.pending && c.stop_work.delay==80);
    expire(&c); assert(!playing && !powered);
    /* Replay the same uploaded effect: each playback must get a new timer. */
    haptics_playback(dev,0,1); run_play(&c);
    assert(playing && powered && c.stop_work.work.pending);
    before=io_count;
    haptics_playback(dev,0,0); assert(io_count==before); run_play(&c);
    assert(!playing && !powered && !c.stop_work.work.pending);
    assert(starts==2);
    /* Rumble must accept either motor channel without requiring FF_CUSTOM. */
    memset(&e,0,sizeof(e)); e.type=FF_RUMBLE; e.replay.length=35;
    e.u.rumble.weak_magnitude=65535;
    assert(haptics_upload_effect(dev,&e,NULL)==0 && amplitude==255);
    assert(!c.stop_work.work.pending);
    haptics_playback(dev,0,1); run_play(&c); assert(c.stop_work.delay==35); expire(&c);
    /* Signed minimum must not overflow the unsigned hardware amplitude. */
    memset(&e,0,sizeof(e)); e.type=FF_CONSTANT; e.u.constant.level=-32768;
    assert(haptics_upload_effect(dev,&e,NULL)==0 && amplitude==255);
    memset(&e,0,sizeof(e)); e.type=FF_PERIODIC; e.u.periodic.waveform=FF_SINE;
    e.u.periodic.magnitude=-32768;
    assert(haptics_upload_effect(dev,&e,NULL)==0 && amplitude==255);
    /* Full 16-bit master gain scales the uploaded amplitude, including mute. */
    e.type=FF_RUMBLE; e.u.rumble.strong_magnitude=32768; e.u.rumble.weak_magnitude=0;
    assert(haptics_upload_effect(dev,&e,NULL)==0 && amplitude==127);
    haptics_set_gain(dev,32768); assert(c.set_gain_work.pending);
    haptics_set_gain_work(&c.set_gain_work); assert(amplitude==63);
    haptics_set_gain(dev,0); haptics_set_gain_work(&c.set_gain_work); assert(amplitude==0);
    haptics_set_gain(dev,65535); haptics_set_gain_work(&c.set_gain_work); assert(amplitude==127);
    /* A failed hardware upload must reach userspace, never report success. */
    load_error=-EIO; int puts_before=pm_puts;
    assert(haptics_upload_effect(dev,&e,NULL)==-EIO && pm_puts==puts_before+1);
    load_error=0;
    assert(haptics_upload_effect(dev,&e,NULL)==0);
    boost_error=-ETIMEDOUT;
    haptics_playback(dev,0,1); run_play(&c);
    assert(!playing && !powered && !c.stop_work.work.pending);
    puts("haptics: standard effects, replay timers, explicit stop, gain and hardware failures passed");
    return 0;
}
'''


def main():
    kernel = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / 'linux'
    source = (kernel / 'drivers/input/misc/qcom-hv-haptics.c').read_text()
    names = ('haptics_stop_constant_effect_play', 'haptics_play_work',
             'haptics_upload_effect', 'haptics_playback',
             'haptics_set_gain_work', 'haptics_set_gain')
    program = MOCKS + '\n'.join(function(source, name) for name in names) + TESTS
    with tempfile.TemporaryDirectory(prefix='negroni-haptics-') as directory:
        path = Path(directory)
        (path / 'test.c').write_text(program)
        subprocess.run([os.environ.get('CC', 'cc'), '-std=gnu11', '-Wall', '-Wextra',
                        '-Werror', '-Wno-unused-parameter', '-Wno-unused-function',
                        str(path / 'test.c'), '-o', str(path / 'test')], check=True)
        subprocess.run([str(path / 'test')], check=True)


if __name__ == '__main__':
    main()
