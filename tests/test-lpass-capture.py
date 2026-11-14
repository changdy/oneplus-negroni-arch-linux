#!/usr/bin/env python3
"""Compile real LPASS mixer callbacks and check multi-channel state transitions.

Usage: python3 tests/test-lpass-capture.py [KERNEL_SOURCE_DIRECTORY]
"""
from pathlib import Path
import os
import re
import subprocess
import sys
import tempfile


def function(source, name):
    start = re.search(r"static int " + re.escape(name) + r"\(", source).start()
    brace = source.index("{", start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


MOCKS = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#define u8 uint8_t
#define u32 uint32_t
#define TX_MACRO_AIF1_CAP 1
#define TX_MACRO_AIF2_CAP 2
#define TX_MACRO_AIF3_CAP 3
#define TX_MACRO_DEC_MAX 8
#define CDC_TXn_TX_PATH_CTL(n) (n)
#define CDC_TXn_PGA_MUTE_MASK 16
#define test_bit(n,p) (!!(*(p) & (1UL << (n))))
#define set_bit(n,p) (*(p) |= 1UL << (n))
#define clear_bit(n,p) (*(p) &= ~(1UL << (n)))
#define for_each_set_bit(n,p,max) for ((n)=0;(n)<(max);(n)++) if (test_bit(n,p))
struct tx_macro {
    unsigned long active_ch_mask[4], active_ch_cnt[4];
    int active_decimator[4]; /* Allows running the regression on the old code. */
};
struct va_macro { unsigned long active_ch_mask[4], active_ch_cnt[4]; };
struct snd_soc_component { void *data; };
struct snd_soc_dapm_context { struct snd_soc_component *component; };
struct snd_soc_dapm_widget { struct snd_soc_dapm_context *dapm; unsigned shift; };
struct soc_mixer_control { unsigned shift; };
struct snd_kcontrol { uintptr_t private_value; struct snd_soc_dapm_widget *widget; };
struct snd_ctl_elem_value { struct { struct { long value[2]; } integer; } value; };
struct snd_soc_dapm_update;
struct snd_soc_dai { struct snd_soc_component *component; int id; };
static unsigned power_updates, mute_seen, mute_values;
static struct snd_soc_dapm_widget *snd_soc_dapm_kcontrol_to_widget(struct snd_kcontrol *k) { return k->widget; }
static struct snd_soc_component *snd_soc_dapm_to_component(struct snd_soc_dapm_context *d) { return d->component; }
static void *snd_soc_component_get_drvdata(struct snd_soc_component *c) { return c->data; }
static void snd_soc_dapm_mixer_update_power(struct snd_soc_dapm_context *d, struct snd_kcontrol *k, unsigned v, struct snd_soc_dapm_update *u) { power_updates++; }
static void snd_soc_component_write_field(struct snd_soc_component *c, unsigned reg, unsigned mask, unsigned value) {
    mute_seen |= 1U << reg;
    if (value) mute_values |= 1U << reg; else mute_values &= ~(1U << reg);
}
static void snd_soc_component_update_bits(struct snd_soc_component *c, unsigned reg, unsigned mask, unsigned value) {
    snd_soc_component_write_field(c,reg,mask,value);
}
"""

TESTS = r"""
typedef int (*control_fn)(struct snd_kcontrol *, struct snd_ctl_elem_value *);
static void transition(control_fn put, control_fn get, struct snd_kcontrol *k,
                       unsigned long *masks, unsigned long *counts, int value) {
    unsigned dai=k->widget->shift, dec=((struct soc_mixer_control *)k->private_value)->shift;
    unsigned before=power_updates;
    bool changed=(test_bit(dec,&masks[dai]) != !!value);
    struct snd_ctl_elem_value v={0}; v.value.integer.value[0]=value;
    assert(put(k,&v)==(int)changed);
    assert(power_updates==before+changed);
    v.value.integer.value[0]=-1; assert(get(k,&v)==0);
    assert(v.value.integer.value[0]==value);
    for (int i=1;i<=3;i++) assert(counts[i]==(unsigned long)__builtin_popcountl(masks[i]));
}
static void exercise(control_fn put, control_fn get, struct snd_soc_component *c,
                     unsigned long *masks, unsigned long *counts) {
    struct snd_soc_dapm_context dapm={c};
    struct snd_soc_dapm_widget widget={&dapm,1};
    struct soc_mixer_control mc={0};
    struct snd_kcontrol k={(uintptr_t)&mc,&widget};
    for (int dai=1;dai<=3;dai++) {
        widget.shift=dai;
        for (int dec=0;dec<8;dec++) {
            mc.shift=dec; transition(put,get,&k,masks,counts,0);
            transition(put,get,&k,masks,counts,1);
            transition(put,get,&k,masks,counts,1);
        }
        assert(masks[dai]==255 && counts[dai]==8);
        /* Re-enable an earlier channel after another was enabled. */
        mc.shift=0; transition(put,get,&k,masks,counts,1);
        /* Disable in a different order, including repeated writes. */
        for (int i=0;i<8;i++) {
            mc.shift=(i*3)%8; transition(put,get,&k,masks,counts,0);
            transition(put,get,&k,masks,counts,0);
        }
        assert(masks[dai]==0 && counts[dai]==0);
    }
}
int main(void) {
    struct tx_macro tx={0}; struct va_macro va={0};
    struct snd_soc_component c={&tx};
    for (int i=0;i<4;i++) tx.active_decimator[i]=-1;
    exercise(tx_macro_tx_mixer_put,tx_macro_tx_mixer_get,&c,tx.active_ch_mask,tx.active_ch_cnt);
    c.data=&va;
    exercise(va_macro_tx_mixer_put,va_macro_tx_mixer_get,&c,va.active_ch_mask,va.active_ch_cnt);
    c.data=&tx; tx.active_ch_mask[1]=(1UL<<0)|(1UL<<3);tx.active_ch_cnt[1]=2;
    struct snd_soc_dai dai={&c,1};
    unsigned count=0,mask=0;
    assert(tx_macro_get_channel_map(&dai,&count,&mask,NULL,NULL)==0);
    assert(count==2 && mask==9);
    assert(tx_macro_digital_mute(&dai,1,1)==0);assert(mute_seen==9 && mute_values==9);
    mute_seen=0;
    assert(tx_macro_digital_mute(&dai,0,1)==0);assert(mute_seen==9 && mute_values==0);
    mute_seen=0;dai.id=2;
    assert(tx_macro_digital_mute(&dai,1,1)==0);assert(mute_seen==0);
    puts("LPASS TX/VA: repeated writes, channel removal, counts, DAI isolation and stereo mute passed");
}
"""


def main():
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "linux"
    codec = root / "sound/soc/codecs"
    tx = (codec / "lpass-tx-macro.c").read_text()
    va = (codec / "lpass-va-macro.c").read_text()
    functions = [function(tx, name) for name in (
        "tx_macro_tx_mixer_get", "tx_macro_tx_mixer_put",
        "tx_macro_get_channel_map", "tx_macro_digital_mute")]
    functions += [function(va, name) for name in ("va_macro_tx_mixer_get", "va_macro_tx_mixer_put")]
    with tempfile.TemporaryDirectory(prefix="negroni-lpass-test-") as temp:
        source = Path(temp) / "capture.c"
        binary = Path(temp) / "capture"
        source.write_text(MOCKS + "\n".join(functions) + TESTS)
        subprocess.run([os.environ.get("CC", "cc"), "-std=c11", "-Wall", "-Wextra",
                        "-Werror", "-Wno-unused-parameter", "-Wno-unused-function", "-Wno-sign-compare",
                        str(source), "-o", str(binary)], check=True)
        subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    main()
