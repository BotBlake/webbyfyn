function createNativeShell(config) {
    "use strict";

    const { appName, appVersion, deviceName, deviceProfile, logPrefix } = config;
    const cloneDeviceProfile = () => structuredClone(deviceProfile);
    const logError = error => console.error(`${logPrefix} ${error.message}`);

    // Qt bridge
    let mpvBridgePromise;
    const getMpvBridge = () => {
        mpvBridgePromise ??= new Promise((resolve, reject) => {
            if (typeof QWebChannel !== "function" || !window.qt?.webChannelTransport) {
                reject(new Error("Qt WebChannel is unavailable"));
            return;
            }

            new QWebChannel(window.qt.webChannelTransport, channel => {
                const bridge = channel.objects.player;
                if (bridge) {
                    resolve(bridge);
                } else {
                    reject(new Error("MPV bridge is unavailable"));
                }
            });
        });
        return mpvBridgePromise;
    };

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

    const sendMpvCommand = async (command, ...args) => {
        const loggedArgs = command === "loadfile" || command === "sub-add"
            ? [redactUrl(args[0]), ...args.slice(1)]
            : args;

        console.info(`${logPrefix} ${JSON.stringify({ command, args: loggedArgs })}`);

        const bridge = await getMpvBridge();
        const accepted = await new Promise(resolve => {
            bridge.dispatch(command, args, resolve);
        });
        if (!accepted) {
            throw new Error(`MPV rejected ${command}`);
        }
    };

    const sendMpvCommandSoon = (command, ...args) => {
        void sendMpvCommand(command, ...args).catch(logError);
    };

    // Jellyfin player plugin
    class MpvVideoPlayer {
        constructor({ events, loading, appRouter, appHost, dashboard }) {
            this.priority = -1;
            this.isLocalPlayer = true;
            this.useFullSubtitleUrls = true;

            this.events = events;
            this.loading = loading;
            this.appRouter = appRouter;
            this.appHost = appHost;
            this._setTransparency = dashboard.default.setBackdropTransparency.bind(
                dashboard.default
            );

            this._src = null;
            this._paused = false;
            this._currentTime = 0;
            this._duration = null;
            this._mediaStreams = [];
            this._volume = 100;
            this._muted = false;
            this._pendingStart = null;
            this._playRequestId = 0;
            this._videoDialog = null;

            this._bridgeReady = getMpvBridge().then(bridge => {
                bridge.playbackStarted.connect(() => this._onPlaybackStarted());
                bridge.playbackEnded.connect(() => this._onPlaybackEnded());
                bridge.playbackFailed.connect(message => this._onPlaybackFailed(message));
                bridge.positionChanged.connect(value => this._onPositionChanged(value));
                bridge.pauseChanged.connect(value => this._onPauseChanged(value));
            });
            void this._bridgeReady.catch(logError);
        }

        canPlayMediaType(mediaType) {
            return String(mediaType || "").toLowerCase() === "video";
        }

        getDeviceProfile(item, options) {
            return this.appHost.getDeviceProfile(item, options);
        }

        supports() {
            return false;
        }

        async play(options) {
            if (!options?.url) {
                throw new Error("Jellyfin did not provide a media URL");
            }

            const playRequestId = ++this._playRequestId;
            const startTicks = Number(options.playerStartPositionTicks) || 0;
            const durationTicks = Number(
                options.mediaSource?.RunTimeTicks ?? options.item?.RunTimeTicks
            ) || 0;

            this._currentTime = startTicks / 10_000;
            this._duration = durationTicks > 0 ? durationTicks / 10_000 : null;
            this._mediaStreams = options.mediaSource?.MediaStreams || [];
            this._cancelPendingStart(new Error("MPV load was replaced"));
            await this._bridgeReady;
            if (playRequestId !== this._playRequestId) {
                throw new Error("MPV load was replaced");
            }

            const src = options.url;
            this._src = src;
            this._paused = false;
            this._createVideoDialog(options);

            const started = new Promise((resolve, reject) => {
                this._pendingStart = { src, playRequestId, resolve, reject };
            });

            try {
                await Promise.all([
                    sendMpvCommand(
                        "loadfile",
                        src,
                        "replace",
                        -1,
                        { start: String(startTicks / 10_000_000) }
                    ),
                    started
                ]);
                if (playRequestId !== this._playRequestId || this._src !== src) {
                    throw new Error("MPV stopped while starting playback");
                }
                this._takePendingStart(src);
            } catch (error) {
                this._takePendingStart(src);
                if (playRequestId === this._playRequestId && this._src === src) {
                    this._resetPlayback();
                }
                this.loading?.hide();
                throw error;
            }

            this.loading?.hide();
            if (options.fullscreen) {
                void this.appRouter.showVideoOsd()
                    .then(() => {
                        if (this._videoDialog) {
                            this._videoDialog.style.zIndex = "unset";
                        }
                    })
                    .catch(logError);
            }
            this.events.trigger(this, "playing");
        }

        async stop() {
            const src = this._src;
            this._cancelPendingStart(new Error("MPV playback was stopped"));
            try {
                await sendMpvCommand("stop");
            } finally {
                this._resetPlayback();
            }
            this.events.trigger(this, "stopped", [{ src }]);
        }

        destroy() {
            this._removeVideoDialog();
        }

        pause() {
            this._paused = true;
            sendMpvCommandSoon("set", "pause", true);
            this.events.trigger(this, "pause");
        }

        unpause() {
            this._paused = false;
            sendMpvCommandSoon("set", "pause", false);
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
                    sendMpvCommandSoon("seek", this._currentTime / 1000, "absolute");
                }
            }
            return this._currentTime;
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
            sendMpvCommandSoon("set", "volume", this._volume);
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
            sendMpvCommandSoon("set", "mute", this._muted);
            this.events.trigger(this, "volumechange");
        }

        isMuted() {
            return this._muted;
        }

        canSetAudioStreamIndex() {
            return false;
        }

        setSubtitleStreamIndex(index) {
            const jellyfinIndex = Number(index);
            if (jellyfinIndex < 0) {
                sendMpvCommandSoon("set", "sid", "no");
                return;
            }

            const stream = this._mediaStreams.find(
                item => item.Type === "Subtitle" && Number(item.Index) === jellyfinIndex
            );
            if (stream?.DeliveryMethod === "External" && stream.DeliveryUrl) {
                sendMpvCommandSoon("sub-add", stream.DeliveryUrl, "select");
                return;
            }

            let relativeIndex = 0;
            for (const item of this._mediaStreams) {
                if (item.Type !== "Subtitle" || item.IsExternal) {
                    continue;
                }

                relativeIndex += 1;
                if (Number(item.Index) === jellyfinIndex) {
                    sendMpvCommandSoon("set", "sid", relativeIndex);
                    return;
                }
            }

            sendMpvCommandSoon("set", "sid", "no");
        }

        // MPV events
        _onPlaybackEnded() {
            if (!this._src) {
                return;
            }

            const src = this._src;
            this._resetPlayback();
            const pending = this._takePendingStart(src);
            if (pending) {
                pending.reject(new Error("MPV ended before playback started"));
                return;
            }
            this.events.trigger(this, "stopped", [{ src }]);
        }

        _onPlaybackFailed(message) {
            if (!this._src) {
                return;
            }

            const src = this._src;
            this._resetPlayback();
            this.loading?.hide();
            const error = new Error(message);
            const pending = this._takePendingStart(src);
            if (pending) {
                pending.reject(error);
            } else {
                this.events.trigger(this, "error", [error]);
            }
        }

        _onPlaybackStarted() {
            const pending = this._pendingStart;
            if (!pending || pending.src !== this._src) {
                return;
            }

            pending.resolve();
        }

        _onPositionChanged(value) {
            const milliseconds = Number(value);
            if (!this._src || !Number.isFinite(milliseconds)) {
                return;
            }

            this._currentTime = Math.max(0, milliseconds);
            this.events.trigger(this, "timeupdate");
        }

        _onPauseChanged(value) {
            if (!this._src) {
                return;
            }

            const paused = Boolean(value);
            if (paused === this._paused) {
                return;
            }

            this._paused = paused;
            this.events.trigger(this, paused ? "pause" : "unpause");
        }

        _takePendingStart(src) {
            if (this._pendingStart?.src !== src) {
                return null;
            }

            const pending = this._pendingStart;
            this._pendingStart = null;
            return pending;
        }

        _cancelPendingStart(error) {
            const pending = this._pendingStart;
            this._pendingStart = null;
            pending?.reject(error);
        }

        _resetPlayback() {
            this._src = null;
            this._paused = false;
            this._removeVideoDialog();
        }

        // Jellyfin's transparent player layer
        _createVideoDialog(options) {
            let dialog = this._videoDialog;
            if (!dialog?.isConnected) {
                dialog = document.createElement("div");
                dialog.classList.add("videoPlayerContainer");
                document.body.prepend(dialog);
            }

            dialog.style.zIndex = options.fullscreen ? "1000" : "unset";
            dialog.style.setProperty("background", "transparent", "important");
            document.body.classList.toggle("hide-scroll", Boolean(options.fullscreen));

            this._videoDialog = dialog;
            this._setTransparency("full");
        }

        _removeVideoDialog() {
            if (document.fullscreenElement) {
                void document.exitFullscreen().catch(logError);
            }
            this._setTransparency("none");
            document.body.classList.remove("hide-scroll");
            this._videoDialog?.remove();
            this._videoDialog = null;
        }
    
        name = "MPV Video Player";
        type = "mediaplayer";
        id = "mpvvideoplayer";
}

    // NativeShell API
    window.mpvVideoPlayer = () => MpvVideoPlayer;

    window.NativeShell = {
        getPlugins: () => ["mpvVideoPlayer"]
    };

    window.NativeShell.AppHost = {
        init() {},
        supports: feature => String(feature).toLowerCase() === "fullscreenchange",
        getDefaultLayout: () => "desktop",
        getDeviceProfile: cloneDeviceProfile,
        getSyncProfile: cloneDeviceProfile,
        appName: () => appName,
        appVersion: () => appVersion,
        deviceName: () => deviceName
    };
}
