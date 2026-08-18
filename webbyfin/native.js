function createNativeShell(config) {
    "use strict";

    const { appName, appVersion, deviceName, deviceProfile, logPrefix } = config;
    const copyDeviceProfile = () => JSON.parse(JSON.stringify(deviceProfile));

    const redactUrl = (value) => {
        try {
            const url = new URL(value, window.location.href);
            url.search = "";
            url.hash = "";
            return url.href;
        } catch {
            return String(value).split(/[?#]/, 1)[0];
        }
    };

    const sendMpvCommand = (command, ...args) => {
        const loggedArgs = command === "loadfile" || command === "sub-add"
            ? [redactUrl(args[0]), ...args.slice(1)]
            : args;

        const message = JSON.stringify({ command, args: loggedArgs });
        console.info(`${logPrefix} ${message}`);
    };

    class MpvVideoPlayer {
        constructor({ events, loading, appHost }) {
            this.name = "MPV Command Logger";
            this.type = "mediaplayer";
            this.id = "mpvvideoplayer";
            this.priority = -1;
            this.isLocalPlayer = true;

            this.events = events;
            this.loading = loading;
            this.appHost = appHost;

            this._src = null;
            this._paused = false;
            this._currentTime = 0;
            this._duration = null;
            this._mediaStreams = [];
            this._volume = 100;
            this._muted = false;
        }

        canPlayMediaType(mediaType) {
            return String(mediaType || "").toLowerCase() === "video";
        }

        canPlayItem(item) {
            return this.canPlayMediaType(item?.MediaType);
        }

        supportsPlayMethod() {
            return true;
        }

        getDeviceProfile(item, options) {
            return this.appHost.getDeviceProfile(item, options);
        }

        async play(options) {
            if (!options?.url) {
                throw new Error("Jellyfin did not provide a media URL");
            }

            const startTicks = Number(options.playerStartPositionTicks) || 0;
            const durationTicks = Number(
                options.mediaSource?.RunTimeTicks ?? options.item?.RunTimeTicks
            ) || 0;

            this._currentTime = startTicks / 10_000;
            this._duration = durationTicks > 0 ? durationTicks / 10_000 : null;
            this._mediaStreams = options.mediaSource?.MediaStreams || [];

            sendMpvCommand(
                "loadfile",
                options.url,
                "replace",
                -1,
                { start: String(startTicks / 10_000_000) }
            );

            this._src = options.url;
            this._paused = false;
            this.loading?.hide();
            this.events.trigger(this, "playing");
        }

        stop() {
            const src = this._src;
            sendMpvCommand("stop");
            this._src = null;
            this._paused = false;
            this.events.trigger(this, "stopped", [{ src }]);
            return Promise.resolve();
        }

        pause() {
            this._paused = true;
            sendMpvCommand("set", "pause", true);
            this.events.trigger(this, "pause");
        }

        unpause() {
            this._paused = false;
            sendMpvCommand("set", "pause", false);
            this.events.trigger(this, "unpause");
        }

        resume() {
            this.unpause();
        }

        paused() {
            return this._paused;
        }

        currentSrc() {
            return this._src;
        }

        currentTime(value) {
            if (value != null) {
                const milliseconds = Number(value);
                if (Number.isFinite(milliseconds)) {
                    this._currentTime = Math.max(0, milliseconds);
                    sendMpvCommand("seek", this._currentTime / 1000, "absolute");
                }
            }
            return this._currentTime;
        }

        currentTimeAsync() {
            return Promise.resolve(this.currentTime());
        }

        duration() {
            return this._duration;
        }

        seekable() {
            return this._duration != null;
        }

        setVolume(value) {
            const volume = Number(value);
            if (!Number.isFinite(volume)) {
                return;
            }

            this._volume = Math.max(0, Math.min(100, volume));
            sendMpvCommand("set", "volume", this._volume);
            this.events.trigger(this, "volumechange");
        }

        getVolume() {
            return this._volume;
        }

        volumeUp() {
            this.setVolume(this._volume + 2);
        }

        volumeDown() {
            this.setVolume(this._volume - 2);
        }

        setMute(value) {
            this._muted = Boolean(value);
            sendMpvCommand("set", "mute", this._muted);
            this.events.trigger(this, "volumechange");
        }

        isMuted() {
            return this._muted;
        }

        setSubtitleStreamIndex(index) {
            const jellyfinIndex = Number(index);
            if (jellyfinIndex < 0) {
                sendMpvCommand("set", "sid", "no");
                return;
            }

            const stream = this._mediaStreams.find(
                item => item.Type === "Subtitle" && Number(item.Index) === jellyfinIndex
            );
            if (stream?.DeliveryMethod === "External" && stream.DeliveryUrl) {
                sendMpvCommand("sub-add", stream.DeliveryUrl, "select");
                return;
            }

            let relativeIndex = 0;
            for (const item of this._mediaStreams) {
                if (item.Type !== "Subtitle" || item.IsExternal) {
                    continue;
                }

                relativeIndex += 1;
                if (Number(item.Index) === jellyfinIndex) {
                    sendMpvCommand("set", "sid", relativeIndex);
                    return;
                }
            }

            sendMpvCommand("set", "sid", "no");
        }

        getBufferedRanges() {
            return [];
        }

        canSetAudioStreamIndex() {
            return false;
        }

        supports() {
            return false;
        }

        destroy() {}
    }

    window.NativeShell = {
        getPlugins: () => ["mpvVideoPlayer"],
        AppHost: {
            init: () => Promise.resolve({ deviceName, appName, appVersion }),
            supports: () => false,
            getDefaultLayout: () => "desktop",
            getDeviceProfile: copyDeviceProfile,
            getSyncProfile: copyDeviceProfile,
            appName: () => appName,
            appVersion: () => appVersion,
            deviceName: () => deviceName
        }
    };

    window.mpvVideoPlayer = () => MpvVideoPlayer;
}
