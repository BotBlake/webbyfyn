CLIENT_NAME = "Webbyfin"
CLIENT_VERSION = "0.1.0"
DEVICE_NAME = CLIENT_NAME
MPV_LOG_PREFIX = f"[{CLIENT_NAME}:mpv]"

DEVICE_PROFILE = {
    "Name": f"{CLIENT_NAME} MPV",
    "MaxStaticBitrate": 1_000_000_000,
    "DirectPlayProfiles": [
        {"Type": "Video"},
        {"Type": "Audio"},
        {"Type": "Photo"},
    ],
    "TranscodingProfiles": [
        {"Type": "Audio"},
        {
            "Type": "Video",
            "Container": "ts",
            "Protocol": "hls",
            "AudioCodec": "aac,mp3,ac3,opus",
            "VideoCodec": "h264,mpeg4,mpeg2video",
        },
        {"Type": "Photo", "Container": "jpeg"},
    ],
    "CodecProfiles": [],
    "ContainerProfiles": [],
    "ResponseProfiles": [],
    "SubtitleProfiles": [],
}
