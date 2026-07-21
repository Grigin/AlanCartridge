"""MIDI -> PT3 for the ZX Spectrum Chip box's AY player (papaya).

Wraps spectrumizer and stamps the header tone-table id papaya expects.
Papaya numbers its note tables differently from Bulba's reference player:
the tuning spectrumizer arranges (and auditions) as table 1 only plays in
the right key on papaya when the header byte says table 2.
"""
from pathlib import Path
import sys

try:
    from spectrumizer.inputs.midi import load_midi
    from spectrumizer.arrange import arrange
except ImportError:  # not pip-installed: use the vendored clone next to this file
    sys.path.insert(0, str(Path(__file__).parent / "spectrumizer-main"))
    from spectrumizer.inputs.midi import load_midi
    from spectrumizer.arrange import arrange

PAPAYA_TONE_TABLE = 2
TONE_TABLE_OFFSET = 0x63  # header byte the PT3 player reads the table id from


def midi_to_pt3(midi_path, out_path=None, *, style="chiptune", **arrange_opts):
    """Arrange a MIDI file into a papaya-ready .pt3 next to it (or at out_path).

    Extra keyword arguments go straight to spectrumizer's arrange()
    (transpose, arps, echo, vibrato, bass, ...). Returns the output Path.
    """
    midi_path = Path(midi_path)
    out_path = Path(out_path) if out_path else midi_path.with_suffix(".pt3")
    arrange_opts.setdefault("auto_transpose", True)
    arrange_opts.setdefault("name", midi_path.stem.upper()[:32])

    pt3, stats = arrange(load_midi(str(midi_path)), style=style, **arrange_opts)
    pt3 = bytearray(pt3)
    pt3[TONE_TABLE_OFFSET] = PAPAYA_TONE_TABLE
    out_path.write_bytes(bytes(pt3))
    print(f"{midi_path.name} -> {out_path.name}  "
          f"({len(pt3)} bytes, tone table {PAPAYA_TONE_TABLE}, {stats})")
    return out_path


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        midi_to_pt3(arg)
