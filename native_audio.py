"""Native audio decoder bridge scoped to ListenFree's public media hosts."""
import json
from urllib.parse import urlsplit
from PySide6.QtCore import QObject, Signal, Slot, QUrl
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QMediaDevices

def stream_allowed(url):
    try:
        parsed=urlsplit(url)
        host=(parsed.hostname or '').lower()
        return parsed.scheme=='https' and not parsed.username and not parsed.password and any(
            host==domain or host.endswith('.'+domain) for domain in ('saavncdn.com','listenfree.in'))
    except ValueError:
        return False

class NativeAudioBridge(QObject):
    updated=Signal(str,str)
    status=Signal(str)
    def __init__(self,page,parent=None):
        super().__init__(parent)
        self.page=page
        self.players={}
        self.enabled=True
        self.master=1.0
        self.device=QMediaDevices.defaultAudioOutput()

    def emit_state(self,key,event,**values):
        self.updated.emit(key,json.dumps(dict(event=event,**values)))

    def entry(self,key):
        if key in self.players: return self.players[key]
        if len(self.players)>=4: return None
        player=QMediaPlayer(self); output=QAudioOutput(self.device,self)
        player.setAudioOutput(output)
        entry={'player':player,'output':output,'url':'','volume':1.0,'muted':False}
        self.players[key]=entry
        player.positionChanged.connect(lambda ms:self.emit_state(key,'time',position=ms/1000))
        player.durationChanged.connect(lambda ms:self.metadata(key))
        player.bufferProgressChanged.connect(lambda value:self.emit_state(key,'buffer',progress=value))
        player.playbackStateChanged.connect(lambda state:self.state_changed(key,state))
        player.mediaStatusChanged.connect(lambda state:self.media_status(key,state))
        player.errorOccurred.connect(lambda error,message:self.error(key,error))
        return entry

    @Slot(str,str,str)
    def command(self,key,action,raw):
        # The channel is installed only for the provider page and has no file/credential APIs.
        if self.page.url().host().lower() not in ('listenfree.in','www.listenfree.in'): return
        if not key.isdigit() or len(key)>6: return
        try: value=json.loads(raw)
        except (ValueError,TypeError): return
        entry=self.entry(key)
        if entry is None: return
        player=entry['player']
        if action=='source':
            if not isinstance(value,str): return
            if not value:
                player.stop(); player.setSource(QUrl()); entry['url']=''; return
            if not stream_allowed(value):
                self.emit_state(key,'error',message='This audio URL is not a supported ListenFree media stream.')
                self.status.emit('This track uses an unsupported stream source. Try another track.')
                return
            if value!=entry['url']:
                entry['url']=value
                player.setSource(QUrl(value))
        elif action=='load':
            self.metadata(key)
        elif action=='play':
            if self.enabled and entry['url']: player.play()
        elif action=='pause': player.pause()
        elif action=='seek':
            if isinstance(value,(int,float)) and 0<=value<=86400:
                player.setPosition(int(value*1000))
                self.emit_state(key,'seeked',position=player.position()/1000)
        elif action=='volume':
            if isinstance(value,(int,float)) and 0<=value<=1:
                entry['volume']=value; self.apply_volume(entry)
        elif action=='muted':
            entry['muted']=bool(value); self.apply_volume(entry)
        elif action=='rate':
            if isinstance(value,(int,float)) and .5<=value<=2: player.setPlaybackRate(value)

    def metadata(self,key):
        if key not in self.players: return
        player=self.players[key]['player']
        if player.duration()>0:
            self.emit_state(key,'metadata',duration=player.duration()/1000,seekable=player.isSeekable())

    def state_changed(self,key,state):
        if state==QMediaPlayer.PlayingState:
            self.emit_state(key,'playing')
            self.status.emit('Playing inside Ascend • native audio')
        elif state==QMediaPlayer.PausedState:
            self.emit_state(key,'pause')

    def media_status(self,key,state):
        if state in (QMediaPlayer.LoadedMedia,QMediaPlayer.BufferedMedia):
            self.metadata(key)
        elif state==QMediaPlayer.EndOfMedia:
            self.emit_state(key,'ended')
        elif state in (QMediaPlayer.BufferingMedia,QMediaPlayer.StalledMedia):
            self.emit_state(key,'waiting')

    def error(self,key,error):
        if error==QMediaPlayer.NoError: return
        self.emit_state(key,'error',message='The native player could not open this audio stream.')
        self.status.emit('This stream could not play. Try another song or reload ListenFree.')

    def apply_volume(self,entry):
        entry['output'].setVolume(0 if entry['muted'] or not self.enabled else entry['volume']*self.master)

    def set_master(self,value):
        self.master=max(0,min(1,value/100))
        for entry in self.players.values(): self.apply_volume(entry)

    def set_device(self,device):
        self.device=device
        for entry in self.players.values(): entry['output'].setDevice(device)

    def set_enabled(self,on):
        self.enabled=on
        for key,entry in self.players.items():
            if not on and entry['player'].playbackState()==QMediaPlayer.PlayingState:
                entry['player'].pause()
            self.apply_volume(entry)

    def reset(self):
        for entry in self.players.values():
            entry['player'].stop()
            entry['player'].deleteLater(); entry['output'].deleteLater()
        self.players.clear()
