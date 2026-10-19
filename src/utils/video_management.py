import os
import time
from pathlib import Path

import ffmpeg

from utils.logger_manager import logger


class VideoManagement:
    @staticmethod
    def trim_incomplete_flv_tag(file):
        """Drop only an unfinished final FLV tag, without decoding or re-encoding."""
        with open(file, "r+b") as stream:
            header = stream.read(9)
            if len(header) != 9 or header[:4] != b"FLV\x01":
                return
            size = stream.seek(0, os.SEEK_END)
            offset = int.from_bytes(header[5:9], "big")
            if offset < 9 or offset + 4 > size:
                return
            stream.seek(offset)
            if stream.read(4) != b"\0" * 4:
                return
            offset += 4
            last_complete = offset
            while offset < size:
                stream.seek(offset)
                tag = stream.read(11)
                if len(tag) < 11:
                    break
                if tag[0] & 0x1F not in (8, 9, 18):
                    return
                tag_size = 11 + int.from_bytes(tag[1:4], "big")
                end = offset + tag_size + 4
                if end > size:
                    break
                stream.seek(end - 4)
                if int.from_bytes(stream.read(4), "big") != tag_size:
                    return
                last_complete = offset = end
            if last_complete < size:
                stream.truncate(last_complete)
                logger.info(
                    f"Removed {size - last_complete} bytes of incomplete FLV tail."
                )

    @staticmethod
    def wait_for_file_release(file, timeout=10):
        """
        Wait until the file is released (not locked anymore) or timeout is reached.
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                with open(file, "ab"):
                    return True
            except PermissionError:
                time.sleep(0.5)
        return False

    @staticmethod
    def convert_flv_to_mp4(file, bitrate=None, ffmpeg_path=None):
        """
        Convert the video from flv format to mp4 format
        """
        logger.info("Converting {} to MP4 format...".format(file))

        if not VideoManagement.wait_for_file_release(file):
            logger.error(
                f"File {file} is still locked after waiting. Skipping conversion."
            )
            return

        try:
            VideoManagement.trim_incomplete_flv_tag(file)
            output_args = {
                "c": "copy",
                "n": None,
            }
            output_file = str(
                Path(file).with_name(Path(file).name.replace("_flv.mp4", ".mp4"))
            )
            if output_file == str(file) or Path(output_file).exists():
                from uuid import uuid4

                output_file = str(
                    Path(file).with_name(f"{Path(file).stem}_{uuid4().hex[:10]}.mp4")
                )
            probe = ffmpeg.probe(str(file))
            if not {"video", "audio"} <= {s["codec_type"] for s in probe["streams"]}:
                logger.error("Source does not contain both video and audio.")
                return None

            if bitrate:
                output_args["b:v"] = bitrate
                del output_args["c"]
                output_args["c:v"] = "libx264"
                output_args["c:a"] = "copy"

            ffmpeg.input(file).output(output_file, **output_args).run(
                quiet=True, cmd=ffmpeg_path or "ffmpeg"
            )
            result = ffmpeg.probe(output_file)
            if (
                not {"video", "audio"} <= {s["codec_type"] for s in result["streams"]}
                or float(result.get("format", {}).get("duration", 0)) <= 0
            ):
                logger.error(
                    "Converted file has no valid video/audio duration; keeping source."
                )
                return None

        except (ffmpeg.Error, OSError) as e:
            logger.error(
                f"ffmpeg conversion failed: {getattr(e, 'stderr', b'') or str(e)}"
            )
            return

        os.remove(file)
        logger.info(f"Finished converting {Path(output_file).resolve()}\n")
        return str(Path(output_file).resolve())
