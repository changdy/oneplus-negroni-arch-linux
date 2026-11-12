#!/usr/bin/python3 -I
# SPDX-License-Identifier: GPL-2.0-only
"""Generate alsatplg sections for in-call music and in-call record front ends.

  incall-topology.py MUSIC_DIR RECORD_DIR MUX_CONFIG > incall.conf

MUSIC_DIR/RECORD_DIR hold the sub-graph files that acdb-query dumped from the
phone's ACDB for StreamRX=INCALL_MUSIC (sg_b00000d6.spf) and
StreamTX=INCALL_RECORD (sg_b00000d0.spf, cal_b00000d0.np). MUX_CONFIG is the
tag data for the record graph's MUX_DEMUX (tag stream_muxdemux 0xC0000027),
which selects uplink, downlink or both.

Unlike the hostless voice graphs these two transfer PCM data with the host
through shared-memory end points, and they have no hardware end point: they
hang off modules of the voice graphs that voice-topology.py emits and must
only be opened while a call's voice graphs are running, and closed first.

  MultiMedia7 (playback, graph 6): host -> decoder -> converter -> MFC 4596,
    whose output goes to input port 2 of MFC 458B in the voice TX stream, so
    the far end hears it. The vendor volume, soft pause and splitter stages
    are left out.
  MultiMedia8 (capture, graph 7): the vendor record graph unchanged. It taps
    output port 3 of the voice splitters 4561 (downlink) and 4560 (uplink,
    after the music mix point).

The kernel builds data connections only inside one graph, so connections that
start in the voice graph are passed as a raw graph-open parameter. The DAPM
route to a back end has no mixer control: it satisfies DPCM without making
the kernel connect the back end's DSP graph to these graphs.

Experimental and untested on hardware unless docs/call-audio.md says so. The
output contains vendor calibration and must stay outside Git.
"""
import argparse
import importlib.util
from pathlib import Path
import struct
import sys

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location(
    "negroni_voice_topology", Path(__file__).resolve().with_name("voice-topology.py"))
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)

PREFIX = "incall"
MUSIC_SG, MUSIC_FE, MUSIC_FE_NAME = 0xB00000D6, 6, "MultiMedia7"
RECORD_SG, RECORD_FE, RECORD_FE_NAME = 0xB00000D0, 7, "MultiMedia8"
# kept music modules: WR_SHARED_MEM_EP, PCM decoder, PCM converter, MFC
MUSIC_MODULES = ((0x458E, 0x07001000), (0x4590, 0x07001005), (0x4591, 0x07001003),
    (0x4596, 0x07001015))
MUSIC_SPLITTER, MUSIC_MIX_POINT = 0x42F2, (0x458B, 2)
RECORD_TAPS = ((0x4561, 3, 0x4558, 2), (0x4560, 3, 0x4222, 2))
RECORD_MUX, RECORD_EP, RECORD_EP_ID = 0x4207, 0x455D, 0x07001001
MUX_OUT_FORMAT = 0x080011BE     # PARAM_ID_MUX_DEMUX_OUT_FORMAT
RAT_ID, PARAM_ID_RAT_MEDIA_FORMAT = 0x07001041, 0x080010D0
# The kernel copies this token into the PCM format it sends to decoders,
# encoders and converters; without it they reject the format (interleaved 0).
# Values as in the base media topology: 1 interleaved, 3 de-interleaved unpacked.
INTERLEAVE_TOKEN = ("AR_TKN_U32_MODULE_FMT_INTERLEAVE", 252)
INTERLEAVE = dict(Playback=dict([(0x07001005, 1), (0x07001003, 3)]),
    Capture=dict([(0x07001003, 1), (0x07001004, 1)]))
# ... and it reads that token only from decoder, encoder and src widgets.
WIDGET_TYPES = dict([(0x07001005, "decoder"), (0x07001004, "encoder"), (0x07001003, "src")])
# module widgets of the back ends in SM8450-OnePlus-10-Pro.m4
SPEAKER_DEVICE_WIDGET = "device20.logger1"      # TERTIARY_MI2S_RX
MIC_DEVICE_WIDGET = base.MIC_DEVICE_WIDGET# TX_CODEC_DMA_TX_3


def name(iid):
    return "%s.m%04x" % (PREFIX, iid)


def block(kind, title, body):
    return kind + '."' + title + '" {\n' + body + "}\n"


def tuples(title, pairs):
    body = ('\ttokens "%s_tokens"\n\ttuples."word.u32_data" {\n' % PREFIX
        + "".join('\t\t%s "%s"\n' % pair for pair in pairs) + "\t}\n")
    return (block("SectionVendorTuples", title + "_tuples", body)
        + block("SectionData", title + "_data", '\ttuples "%s_tuples"\n' % title))


class Graph:
    def __init__(self, label, fe, fe_name, stream, source, modules):
        self.label, self.fe, self.fe_name, self.stream = label, fe, fe_name, stream
        self.mods = dict((i, dict(source.mods[i])) for i in modules)
        self.sgs = dict((g, source.sgs[g]) for g in set(m["sg"] for m in self.mods.values()))
        self.conts = dict((c, source.conts[c]) for c in set(m["cont"] for m in self.mods.values()))
        self.conns = []
        self.blobs = dict()
        self.routes = []
        self.aif = None

    def add_blob(self, iid, kind, payload):
        if payload:
            self.blobs.setdefault(iid, []).append((kind, payload))


def load(directory, sg):
    return base.Voice.parse_one("%s/sg_%08x.spf" % (directory, sg), "rx")


def music_graph(directory):
    source = load(directory, MUSIC_SG)
    found = tuple((i, source.mods.get(i, dict()).get("id")) for i, _ in MUSIC_MODULES)
    if found != MUSIC_MODULES:
        raise ValueError("unsupported ACDB: in-call music modules differ")
    if (MUSIC_SPLITTER, 3) + MUSIC_MIX_POINT not in source.conns:
        raise ValueError("unsupported ACDB: in-call music mix point differs")
    order = [i for i, _ in MUSIC_MODULES]
    graph = Graph("music", MUSIC_FE, MUSIC_FE_NAME, "Playback", source, order)
    graph.conns = [(a, 1, b, 2) for a, b in zip(order, order[1:])]
    # cross-graph: the kernel emits destination tokens without checking the graph
    graph.conns.append((order[-1], 1) + MUSIC_MIX_POINT)
    graph.aif = (order[0], "aif_in")
    graph.routes = ['"%s, , %s"' % (SPEAKER_DEVICE_WIDGET, name(order[-1]))]
    return graph


def rat_media_format(graph, settings):
    """PARAM_ID_RAT_MEDIA_FORMAT for the rate adapted timer after the MUX_DEMUX.

    The ACDB has no value for it (Android's PAL sets it at run time) and the
    timer refuses to start without one. Use what the MUX_DEMUX is told to
    output: the tap converters' rate and the channels of its output format.
    """
    timers = [i for i, m in graph.mods.items() if m["id"] == RAT_ID]
    formats = [pl for i, p, pl in settings if i == RECORD_MUX and p == MUX_OUT_FORMAT]
    rates = set(struct.unpack_from("<I", pl)[0] for i, p, pl in settings
        if p == base.PARAM_ID_MFC_OUTPUT_MEDIA_FORMAT and (i, 1, RECORD_MUX) in
        [(c[0], c[1], c[2]) for c in graph.conns])
    if len(timers) != 1 or len(formats) != 1 or len(rates) != 1:
        raise ValueError("unsupported ACDB: cannot derive the record timer format")
    bits, q_factor, channels = struct.unpack_from("<HHH", formats[0], 8)
    channel_map = struct.unpack_from("<%dH" % channels, formats[0], 16)
    payload = struct.pack("<IHHII%dH" % channels, rates.pop(), bits, q_factor, 1, channels,
        *channel_map)
    return (timers[0], PARAM_ID_RAT_MEDIA_FORMAT, payload)


def record_graph(directory, mux_config):
    source = load(directory, RECORD_SG)
    if source.mods.get(RECORD_EP, dict()).get("id") != RECORD_EP_ID or RECORD_MUX not in source.mods:
        raise ValueError("unsupported ACDB: in-call record modules differ")
    graph = Graph("record", RECORD_FE, RECORD_FE_NAME, "Capture", source, sorted(source.mods))
    graph.conns = sorted(c for c in source.conns if c[0] in graph.mods)
    taps = sorted(c for c in source.conns if c[0] not in graph.mods)
    if taps != sorted(RECORD_TAPS) or any(c[2] not in graph.mods for c in source.conns):
        raise ValueError("unsupported ACDB: in-call record taps differ")
    links = [c for c in source.ctrl if c[0] in graph.mods or c[2] in graph.mods]
    if len(set(c[:4] for c in links)) != len(links):
        raise ValueError("unsupported ACDB: duplicate in-call record control link")
    opened = base.param(base.APM_IID, base.PID_MOD_CONN,
        struct.pack("<I", len(taps)) + b"".join(struct.pack("<4I", *c) for c in taps))
    if links:
        opened += base.param(base.APM_IID, base.PID_CTRL_LINK,
            struct.pack("<I", len(links)) + b"".join(c[4] for c in links))
    graph.add_blob(RECORD_EP, base.CFG_GRAPH_OPEN, opened)
    settings = base.params(open("%s/cal_%08x.np" % (directory, RECORD_SG), "rb").read())
    settings += base.params(open(mux_config, "rb").read())
    settings.append(rat_media_format(graph, settings))
    unknown = sorted(set(i for i, _, _ in settings if i not in graph.mods))
    if unknown or not any(i == RECORD_MUX for i, _, _ in settings):
        raise ValueError("in-call record settings name other modules: %s" % unknown)
    # One array per module: the kernel sends a module's raw settings right after
    # its own media format for that module, so these win over its defaults.
    for iid in sorted(graph.mods):
        graph.add_blob(iid, base.CFG_SET,
            b"".join(base.param(i, p, pl) for i, p, pl in settings if i == iid))
    graph.aif = (RECORD_EP, "aif_out")
    graph.routes = ['"%s, , %s"' % (name(c[2]), MIC_DEVICE_WIDGET) for c in taps[:1]]
    return graph


def emit_module(graph, iid, module):
    links = [c for c in graph.conns if c[0] == iid]
    pairs = [("AR_TKN_U32_MODULE_INSTANCE_ID", "0x%x" % iid),
        ("AR_TKN_U32_MODULE_ID", "0x%08x" % module["id"]),
        ("AR_TKN_U32_MODULE_MAX_IP_PORTS", module["ports"][0]),
        ("AR_TKN_U32_MODULE_MAX_OP_PORTS", module["ports"][1]),
        ("AR_TKN_U32_MODULE_SRC_INSTANCE_ID", "0x%x" % iid)]
    if module["id"] in INTERLEAVE[graph.stream]:
        pairs.append((INTERLEAVE_TOKEN[0], INTERLEAVE[graph.stream][module["id"]]))
    for n, (_, source_port, destination, destination_port) in enumerate(links):
        suffix = "" if n == 0 else str(n)
        pairs += [("AR_TKN_U32_MODULE_SRC_OP_PORT_ID" + suffix, source_port),
            ("AR_TKN_U32_MODULE_DST_IN_PORT_ID" + suffix, destination_port),
            ("AR_TKN_U32_MODULE_DST_INSTANCE_ID" + suffix, "0x%x" % destination)]
    out = [tuples(name(iid), pairs)]
    data = ["%s.sg%08x_data" % (PREFIX, module["sg"]), "%s.c%08x_data" % (PREFIX, module["cont"]),
        name(iid) + "_data"]
    for n, (kind, payload) in enumerate(graph.blobs.get(iid, [])):
        array = base.cfg_array(kind, payload)
        if len(array) > base.DATA_CHUNK:
            raise ValueError("configuration array for %#x is too large" % iid)
        out.append(block("SectionData", "%s_cfg%d" % (name(iid), n),
            '\tbytes "%s"\n' % base.hexbytes(array)))
        data.append("%s_cfg%d" % (name(iid), n))
    kind = '\ttype "%s"\n' % WIDGET_TYPES.get(module["id"], "buffer")
    if graph.aif[0] == iid:
        kind = '\ttype "%s"\n\tstream_name "%s %s"\n' % (graph.aif[1], graph.fe_name, graph.stream)
    out.append(block("SectionWidget", name(iid),
        '\tindex "%d"\n%s\tno_pm "true"\n\tsubseq "10"\n\tdata [\n%s\t]\n'
        % (graph.fe, kind, "".join('\t\t"%s"\n' % d for d in data))))
    return "".join(out)


def emit_graph(graph):
    out = []
    for sg, pr in sorted(graph.sgs.items()):
        out.append(tuples("%s.sg%08x" % (PREFIX, sg), [
            ("AR_TKN_U32_SUB_GRAPH_INSTANCE_ID", "0x%08x" % sg), ("AR_TKN_DAI_INDEX", graph.fe),
            ("AR_TKN_U32_SUB_GRAPH_PERF_MODE", "0x%x" % pr[base.SG_PROP_PERF][0]),
            ("AR_TKN_U32_SUB_GRAPH_DIRECTION", "0x%x" % pr[base.SG_PROP_DIR][0]),
            ("AR_TKN_U32_SUB_GRAPH_SCENARIO_ID", "0x%x" % pr[base.SG_PROP_SID][0])]))
    for cont, pr in sorted(graph.conts.items()):
        out.append(tuples("%s.c%08x" % (PREFIX, cont), [
            ("AR_TKN_U32_CONAINER_INSTANCE_ID", "0x%08x" % cont),
            ("AR_TKN_U32_CONAINER_CAPABILITY_ID", "0x%x" % pr[base.CONT_TYPE][1]),
            ("AR_TKN_U32_CONAINER_STACK_SIZE", pr[base.CONT_STACK][0]),
            ("AR_TKN_U32_CONAINER_GRAPH_POS", "0x%x" % pr[base.CONT_POS][0]),
            ("AR_TKN_U32_CONAINER_PROC_DOMAIN", "0x%x" % pr[base.CONT_DOMAIN][0])]))
    for iid, module in sorted(graph.mods.items()):
        out.append(emit_module(graph, iid, module))
    lines = sorted(set('"%s, , %s"' % (name(c[2]), name(c[0])) for c in graph.conns
        if c[2] in graph.mods)) + graph.routes
    out.append(block("SectionGraph", "%s %s Graph" % (PREFIX, graph.label),
        '\tindex "%d"\n\tlines [\n%s\t]\n' % (graph.fe, "".join("\t\t%s\n" % l for l in lines))))
    direction = graph.stream.lower()
    title = "%s %s" % (graph.fe_name, graph.stream)
    out.append(block("SectionPCMCapabilities", title,
        '\tformats "S16_LE"\n\trate_min "8000"\n\trate_max "48000"\n'
        '\tchannels_min "1"\n\tchannels_max "2"\n'))
    pcm = "%s InCall" % graph.fe_name
    out.append(block("SectionPCM", pcm,
        '\tindex "%d"\n\tid "%d"\n\tdai."%s" {\n\t\tid "%d"\n\t}\n'
        '\tpcm."%s" {\n\t\tcapabilities "%s"\n\t}\n'
        % (graph.fe, graph.fe, pcm, graph.fe, direction, title)))
    return "".join(out)


def emit(graphs):
    head = ("# In-call music/record graphs from the vendor ACDB (incall-topology.py).\n"
        "# Contains vendor calibration: local use only.\n")
    tokens = block("SectionVendorTokens", PREFIX + "_tokens",
        "".join('\t%s "%s"\n' % token for token in base.TOKENS + [INTERLEAVE_TOKEN]))
    return head + tokens + "".join(emit_graph(g) for g in graphs)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("music_dir")
    parser.add_argument("record_dir")
    parser.add_argument("mux_config")
    args = parser.parse_args()
    graphs = [music_graph(args.music_dir), record_graph(args.record_dir, args.mux_config)]
    for graph in graphs:
        sys.stderr.write("incall %s: %d modules, %d connections, %d arrays\n" % (
            graph.label, len(graph.mods), len(graph.conns), sum(map(len, graph.blobs.values()))))
    sys.stdout.write(emit(graphs))


if __name__ == "__main__":
    main()
