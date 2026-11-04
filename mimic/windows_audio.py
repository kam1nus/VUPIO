"""Windows WASAPI playback and voice mixing through an installed virtual cable."""
from collections import deque
import threading
import wave

import numpy as np


RATE = 48000
VIRTUAL_UID = 'MIMICAudioDevice_UID'


def cable(name):
    name = name.casefold()
    return 'vb-audio' in name or 'virtual cable' in name or 'cable input' in name or 'cable output' in name


class WindowsAudio:
    def __init__(self, sounddevice=None):
        if sounddevice is None:
            import sounddevice
        self.sd = sounddevice
        self.control = threading.RLock()
        self.mix_lock = threading.Lock()
        self.outputs, self.inputs = {}, {}
        self.clips = {}
        self.voice = deque(maxlen=12)
        self.voice_tail = np.empty((0, 1), dtype=np.float32)
        self.monitor_frames = deque(maxlen=12)
        self.player = self.capture = self.monitor = None
        self.output = self.input = self.monitor_device = 0
        self.volume, self.gain, self.parallel = .65, .7, False
        self.clip_peak = self.mic_peak = self.output_peak = 0.
        self.refresh()
        self.output = self.virtual_output or self.default_output

    def refresh(self):
        outputs, inputs = {}, {}
        hosts = self.sd.query_hostapis()
        self.default_output = self.virtual_output = 0
        for index, device in enumerate(self.sd.query_devices()):
            host = hosts[device['hostapi']]
            if 'WASAPI' not in host['name']:
                continue
            # The HTTP contract reserves zero for "no device".
            id = index + 1
            name = device['name']
            row = {'id': id, 'name': name, 'uid': 'wasapi:' + name, 'virtual': cable(name)}
            if device['max_output_channels']:
                outputs[id] = (row, min(2, device['max_output_channels']))
                if index == host['default_output_device'] and not row['virtual']:
                    self.default_output = id
                if row['virtual'] and not self.virtual_output:
                    self.virtual_output = id
            if device['max_input_channels'] and not row['virtual'] and not device.get('is_loopback'):
                inputs[id] = row
        if self.virtual_output:
            outputs[self.virtual_output][0]['uid'] = VIRTUAL_UID
        self.outputs, self.inputs = outputs, inputs
        if not self.default_output:
            self.default_output = next((id for id,(row,_) in outputs.items() if not row['virtual']),0)
        if not self.input:
            self.input = next(iter(inputs), 0)
        if not self.monitor_device:
            self.monitor_device = self.default_output

    @staticmethod
    def close_stream(stream):
        if stream is not None:
            try:
                stream.abort()
            finally:
                stream.close()

    def start_output(self, id, callback):
        stream = self.sd.OutputStream(device=id-1, channels=self.outputs[id][1],
                                      samplerate=RATE, dtype='float32', blocksize=480,
                                      extra_settings=self.sd.WasapiSettings(auto_convert=True), callback=callback)
        try:
            stream.start()
        except Exception:
            stream.close()
            raise
        return stream

    def ensure_output(self):
        if self.player is None or not self.player.active:
            self.close_stream(self.player)
            self.player = None
            if self.output not in self.outputs:
                self.refresh()
                self.output = self.virtual_output or self.default_output
            if not self.output:
                raise ValueError('Выберите доступный аудиовыход Windows.')
            self.player = self.start_output(self.output, self.render)

    @staticmethod
    def map_clip(path):
        with open(path, 'rb') as file, wave.open(file, 'rb') as pcm:
            if pcm.getsampwidth() != 2 or pcm.getframerate() != RATE or pcm.getnchannels() != 2 or not pcm.getnframes():
                raise ValueError('Ожидается стерео WAV PCM 16 бит, 48 кГц.')
            return np.memmap(file, dtype='<i2', mode='r', offset=file.tell(), shape=(pcm.getnframes(), 2))

    def render(self, out, frames, _time, _status):
        mix = np.zeros((frames, 2), dtype=np.float32)
        with self.mix_lock:
            for id, (audio, start) in list(self.clips.items()):
                segment = audio[start:start+frames]
                mix[:len(segment)] += segment
                if start + frames >= len(audio):
                    del self.clips[id]
                else:
                    self.clips[id] = audio, start + frames
            mix *= self.volume / 32768
            self.clip_peak = float(np.max(np.abs(mix)))
            if self.monitor is not None:
                self.monitor_frames.append(mix.copy())
            offset = 0
            while self.capture is not None and offset < frames:
                if len(self.voice_tail) == 0:
                    if not self.voice:
                        break
                    self.voice_tail = self.voice.popleft()
                amount = min(frames-offset, len(self.voice_tail))
                mix[offset:offset+amount] += self.voice_tail[:amount] * self.gain
                self.voice_tail = self.voice_tail[amount:]
                offset += amount
            np.clip(mix, -.98, .98, out=mix)
            self.output_peak = float(np.max(np.abs(mix)))
            self.write(out, mix)

    @staticmethod
    def write(out, mix):
        if out.shape[1] == 1:
            out[:,0] = mix.mean(axis=1)
        else:
            out[:] = mix

    def render_monitor(self, out, frames, _time, _status):
        out.fill(0)
        with self.mix_lock:
            if self.monitor_frames:
                mix = self.monitor_frames.popleft()[:frames]
                self.write(out[:len(mix)], mix)

    def receive(self, data, _frames, _time, _status):
        with self.mix_lock:
            if self.capture is not None:
                self.mic_peak = float(np.max(np.abs(data)))
                self.voice.append(data.copy())

    def stop_mic(self):
        with self.mix_lock:
            stream, self.capture = self.capture, None
            self.voice.clear()
            self.voice_tail = self.voice_tail[:0]
            self.mic_peak = 0.
        self.close_stream(stream)

    def start_mic(self):
        if not self.outputs.get(self.output, ({},0))[0].get('virtual'):
            raise ValueError('Выберите CABLE Input как выход MIMIC перед включением голоса.')
        if self.input not in self.inputs:
            raise ValueError('Выберите доступный физический микрофон.')
        self.ensure_output()
        self.stop_mic()
        stream = self.sd.InputStream(device=self.input-1, channels=1, samplerate=RATE,
                                     blocksize=480, dtype='float32', callback=self.receive,
                                     extra_settings=self.sd.WasapiSettings(auto_convert=True))
        self.capture = stream
        try:
            stream.start()
        except Exception:
            self.stop_mic()
            raise

    def stop(self):
        with self.mix_lock:
            self.clips.clear()
            self.monitor_frames.clear()

    def status(self):
        with self.mix_lock:
            active = list(self.clips)
            output = self.outputs.get(self.output, ({},0))[0]
            running = self.player is not None and self.player.active
            mic = self.capture is not None and self.capture.active
            return dict(platform='windows', playing=active[-1] if active else None, activeClips=active,
                        running=running, mic=mic, micRequested=mic, volume=self.volume,
                        micGain=self.gain, polyphony=self.parallel, output=self.output,
                        outputName=output.get('name','Выберите выход Windows'), outputUID=output.get('uid',''),
                        input=self.input, inputUID=self.inputs.get(self.input, {}).get('uid',''),
                        monitor=self.monitor is not None, monitorDevice=self.monitor_device,
                        driverRegistered=bool(self.virtual_output), virtualConnected=bool(running and output.get('virtual')),
                        physicalMicLevel=self.mic_peak if mic else 0, mixerOutputLevel=self.output_peak if running else 0,
                        clipLevel=self.clip_peak, captureProcess='WASAPI')

    def command(self, op, **data):
        with self.control:
            try:
                return self._command(op, data)
            except self.sd.PortAudioError as error:
                raise ValueError('WASAPI: '+str(error)+'. Проверьте устройство и разрешения Windows.') from error

    def _command(self, op, data):
        if op == 'devices':
            self.refresh()
            return {'devices':[row for row,_ in self.outputs.values()], 'physicalInputs':list(self.inputs.values())}
        if op == 'play':
            self.ensure_output()
            audio = self.map_clip(data['path'])
            with self.mix_lock:
                if not self.parallel:
                    self.clips.clear()
                self.clips.pop(data['id'], None)
                if len(self.clips) >= 8:
                    del self.clips[next(iter(self.clips))]
                self.clips[data['id']] = audio, 0
        elif op == 'stop':
            self.stop()
        elif op == 'panic':
            self.close()
        elif op == 'volume':
            self.volume = min(1., max(0., float(data['value'])))
        elif op == 'output':
            if data['device'] not in self.outputs:
                raise ValueError('Выход WASAPI недоступен. Обновите список устройств.')
            self.close()
            self.output = data['device']
            if data.get('start', True):
                self.ensure_output()
        elif op in {'input', 'mic'}:
            id = data.get('device', self.input)
            if id != self.input:
                if id not in self.inputs:
                    raise ValueError('Вход WASAPI недоступен.')
                active = self.capture is not None
                self.stop_mic()
                self.input = id
                if op == 'input' and active:
                    self.start_mic()
            if op == 'mic':
                self.gain = min(1., max(0., float(data.get('gain',self.gain))))
                if data.get('enabled'):
                    self.start_mic()
                else:
                    self.stop_mic()
        elif op == 'mixer':
            self.parallel = data.get('polyphony', self.parallel)
            self.gain = min(1., max(0., float(data.get('gain',self.gain))))
            if 'monitor' in data:
                stream, self.monitor = self.monitor, None
                self.close_stream(stream)
                with self.mix_lock:
                    self.monitor_frames.clear()
                if data['monitor']:
                    id = data.get('monitorDevice') or self.default_output
                    if id == self.output or id not in self.outputs or self.outputs[id][0]['virtual']:
                        raise ValueError('Для мониторинга выберите отдельные наушники или динамики.')
                    self.ensure_output()
                    self.monitor = self.start_output(id,self.render_monitor)
                    self.monitor_device = id
        elif op != 'status':
            raise ValueError('Эта проверка доступна на Mac. В Windows проверьте уровень микрофона и Mic Test в Discord.')
        return self.status()

    def emergency_mute(self):
        self.command('panic')

    def close(self):
        with self.control:
            self.stop()
            self.stop_mic()
            monitor, self.monitor = self.monitor, None
            player, self.player = self.player, None
            self.close_stream(monitor)
            self.close_stream(player)
