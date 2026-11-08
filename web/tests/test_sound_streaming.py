"""Compile the actual loader policy and check browser/native sound routing."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class SoundStreamingPolicyTests(unittest.TestCase):
    def test_loop_capable_misc_effects_decode_but_dialogue_still_streams(self):
        compiler = shutil.which('cc')
        if not compiler:
            self.skipTest('existing C compiler required; no tool installation')
        source = Path(__file__).resolve().parents[1] / 'engine-mp/codemp/client/snd_mem.cpp'
        text = source.read_text()
        start = text.index('#define SOUND_CHARS_DIR ')
        end = text.index('\n}', text.index('static qboolean S_LoadSound_DirIsAllowedToKeepMP3s', start)) + 2
        policy = text[start:end]
        prefix = '''#define _GNU_SOURCE
#include <string.h>
#include <strings.h>
#include <assert.h>
typedef int qboolean;
#define qtrue 1
#define qfalse 0
#define Q_stricmpn strncasecmp
#define Q_stristr strcasestr
'''
        checks = '''
int main(void) {
 assert(S_LoadSound_DirIsAllowedToKeepMP3s("sound/chars/tauntaun/misc/buck2") == EXPECT_MISC);
 assert(S_LoadSound_DirIsAllowedToKeepMP3s("SOUND/CHARS/TAUNTAUN/MISC/BUCK2.MP3") == EXPECT_MISC);
 assert(S_LoadSound_DirIsAllowedToKeepMP3s("sound/chars/kyle/misc/pain25.mp3") == EXPECT_MISC);
 assert(S_LoadSound_DirIsAllowedToKeepMP3s("sound/chars/kyle/dialogue/line.mp3") == 1);
 assert(S_LoadSound_DirIsAllowedToKeepMP3s("sound/ambience/wind.mp3") == 0);
 return 0;
}
'''
        with tempfile.TemporaryDirectory() as d:
            file = Path(d, 'policy.c'); file.write_text(prefix + policy + checks)
            for browser in (False, True):
                exe = Path(d, 'test')
                args = [compiler, '-std=c11', '-DEXPECT_MISC=' + ('0' if browser else '1')]
                if browser:
                    args.append('-D__EMSCRIPTEN__')
                subprocess.run(args + [str(file), '-o', str(exe)], check=True, capture_output=True)
                result = subprocess.run([str(exe)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
