#!/usr/bin/env python3
#
##############################################################################
### NZBGET POST-PROCESSING SCRIPT                                          ###

# Convert Video files using fmpeg to x265.
#
# This script converts video files from the download directory using ffmpeg to
# x265 using a configurable CRF per video resolution.
#
# NOTE: This script requires Python to be installed on your system.
# Requires:
# - ffmpeg-python (pip install ffmpeg-python) and ffmpeg
# - filedate (pip install filedate)
# - pymkv (pip install pymkv) and MKVToolNix
# Linux only!

##############################################################################
### OPTIONS                                                                ###

# Extensions To Check
#
# Comma seperated list of extensions to check files are queued by tdarr.
#extensions_to_check=mkv,mp4,mov,m4v,mpg,mpeg,avi,flv,webm,wmv,vob,evo,iso,m2ts,ts

# CRF value for 480p and 576p content.
#
# Defaults to 19 (0-51, lower = higher quality, bigger file)
#sdCRF=19

# CRF value for 720p content.
#
# Defaults to 20 (0-51, lower = higher quality, bigger file)
#hdCRF=20

# CRF value for 1080p content.
#
# Defaults to 21 (0-51, lower = higher quality, bigger file)
#fullhdCRF=21

# CRF value for 4K/UHD/2160p content.
#
# Defaults to 23 (0-51, lower = higher quality, bigger file)
#uhdCRF=23

# rc-lookahead
#
# Amount of rc-lookahead to use, 0-250, defaults to 20.
#rclookahead=20

# aq-mode
#
# Value of aq-mode to use, 0-4, defaults to 2.
#aqmode=2

# ffmpeg preset
#
# ffmpeg preset to use (slow, medium, fat, veryfast), defaults to medium.
#ffmpegPreset=medium

# Minimum Video trancode size
#
# Minimum percentage allowed for video file. If the trancoded file is smaller
# then this percentage. It will keep the original file. Defaults to 10.
#minPercent=10

# Maximum Video trancode size
#
# Maximum percentage allowed for video file. If the trancoded file is larger
# then this percentage. It will keep the original file. Defaults to 125.
#maxPercent=100

# Retry on a failed transcode.
#
# Number of times to retry transcoding on failure, defaults to 1. Set to 0 for
# no retries.
#retryFailure=1

# Convert DTS to EAC3 5.1 640k
#
# Will convert DTS audio to EAC3 5.1 768k when True (and not when False).
#convertDTS=True

### NZBGET POST-PROCESSING SCRIPT                                          ###
##############################################################################

# TODO: Add option to force 8 or 10 bit encoding?
# name: 'force10bit',
# defaultValue: false,
# tooltip: `Specify if output file should be forced to 10bit. Default is false (bit depth is same as source).

import os
import sys
import ffmpeg
import filedate
from pymkv import MKVFile
# for printing Python dictionaries in a human-readable way
from pprint import pprint

# Should be false, except when debugging/testing outside nzbget.
skipNZBChecks=False

# NZBGet V11+
# Check if the script is called from nzbget 11.0 or later
if skipNZBChecks or 'NZBOP_SCRIPTDIR' in os.environ and not os.environ['NZBOP_VERSION'][0:5] < '11.0':
    # Exit codes used by NZBGet
    POSTPROCESS_PARCHECK=92
    POSTPROCESS_SUCCESS=93
    POSTPROCESS_ERROR=94
    POSTPROCESS_NONE=95

    # Helper function to set and re-initialize ffmpeg kwargs options.
    def initkwargs():
        kwargs={}
        if skipNZBChecks:
            kwargs['c:a']='copy'
            kwargs['rc-lookahead']="20"
            kwargs['aq-mode']="2"
            kwargs['preset']="medium"
        else:
            kwargs['rc-lookahead']=os.environ['NZBPO_RCLOOKAHEAD']
            kwargs['aq-mode']=os.environ['NZBPO_AQMODE']
            kwargs['preset']=os.environ['NZBPO_FFMPEGPRESET']
        # Default to copy the audio tracks.
        kwargs['c:a']='copy'
        return(kwargs)

    # Allow debugging mode when skipNZBChecks is true.
    if skipNZBChecks:
        print ("[INFO] Script triggered from outisde NZBGet.")
        # Define variables for testing outside of nzbget.
        process_directory="/path/sonarr/test"
        #process_directory="/home/nate/Videos/TV"
        extensions_to_check="mkv,mp4,mov,m4v,mpg,mpeg,avi,flv,webm,wmv,vob,evo,iso,m2ts,ts"
        sdCRF="19"
        hdCRF="20"
        fullhdCRF="21"
        uhdCRF="23"
        minPercent=10
        maxPercent=100
        # retryFailure = 1 for no retries or 0 to skip ffmpeg transcoding.
        retryFailure=2
        convertDTS='true'
        print ("[INFO] Option variables set.")
    else:
        print ("[INFO] Script triggered from NZBGet (11.0 or later).")
        # Check if destination directory exists (important for reprocessing of history items)
        if not os.path.isdir(os.environ['NZBPP_DIRECTORY']):
            print ("[ERROR] Nothing to post-process: destination directory", os.environ['NZBPP_DIRECTORY'], "doesn't exist")
            sys.exit(POSTPROCESS_ERROR)
        process_directory=os.environ['NZBPP_DIRECTORY']
        # Set the option variables.
        extensions_to_check = os.environ['NZBPO_EXTENSIONS_TO_CHECK']
        sdCRF = os.environ['NZBPO_SDCRF']
        hdCRF = os.environ['NZBPO_HDCRF']
        fullhdCRF = os.environ['NZBPO_FULLHDCRF']
        uhdCRF = os.environ['NZBPO_UHDCRF']
        minPercent=int(os.environ['NZBPO_MINPERCENT'])
        maxPercent=int(os.environ['NZBPO_MAXPERCENT'])
        retryFailure=int(os.environ['NZBPO_RETRYFAILURE']) + 1
        convertDTS=os.environ['NZBPO_CONVERTDTS']
        if (convertDTS.strip().lower() != 'true' ):
            convertDTS = False
        else:
            convertDTS = True
        print ("[INFO] Option variables set.")

    # Make sure the extensions to check starts with a period.
    extensionsToProcess = []
    for ext in extensions_to_check.split(','):
        if ext.startswith('.'):
            extensionsToProcess.append(ext)
        else:
            extensionsToProcess.append("."+ext)

    # Helper function to Setup file data required for processing.
    def emptyFiletoProcess(file):
        files_to_process = {}
        files_to_process['file'] = file
        files_to_process['converted_file'] = ""
        files_to_process['attempts'] = 0
        files_to_process['video_streams'] = []
        files_to_process['audio_streams'] = []
        files_to_process['stream_data'] = {}
        files_to_process['failed'] = False
        return files_to_process

    # Helper function to get file path, name, and extension
    def getFilePathinfo(file):
        file_path = os.path.dirname(file)
        file_name = os.path.basename(file)
        file_name, file_extension = os.path.splitext(file_name)
        return file_path, file_name, file_extension

    # Helper function to get stream info.
    def getStreams(file):
        # Get video info with ffprobe
        probe = ffmpeg.probe(file)
        stream_data = probe
        video_streams = []
        audio_streams = []
        for stream in probe['streams']:
            if stream['codec_type'] == 'video':
                video_streams.append(stream)
            elif stream['codec_type'] == 'audio':
                audio_streams.append(stream)
        return stream_data, video_streams, audio_streams

    # Helper function to get crf per height and width.
    def getCRF(height, width):
        # SD (Standard Definition) 	480p 	4:3 	640 x 480
        # HD (High Definition) 	720p 	16:9 	1280 x 720
        # Full HD (FHD) 	1080p 	16:9 	1920 x 1080
        # QHD (Quad HD) 	1440p 	16:9 	2560 x 1440
        # 2K video 	1080p 	1:1.77 	2048 x 1080
        # 4K video or Ultra HD (UHD) 	4K or 2160p 	1:1.9 	3840 x 2160
        # 8K video or Full Ultra HD 	8K or 4320p 	16∶9 	7680 x 4320
        if width <= 640:
            crf=sdCRF
        elif width <= 1280:
            crf=hdCRF
        elif width <= 1920:
            crf=fullhdCRF
        elif width <= 3840:
            crf=uhdCRF
        else:
            print ("[ERROR] Could not set crf for video with height:", height, ", and width:", width)
            sys.exit(POSTPROCESS_ERROR)
        return crf

    # Helper function to get a new and unsused file name with mkv extension.
    def getNewFileName(file, counter=1, ext=".mkv"):
        file_path, file_name, file_extension = getFilePathinfo(file)
        new_file=file_name+"("+str(counter)+")"+ext
        if os.path.exists(os.path.join(file_path, new_file)):
            counter += 1
            new_file = getNewFileName(file, counter)
        return os.path.join(file_path, new_file)

    # Get all the files we will need to process and the stream details.
    files_to_process = {}
    print ("[INFO] Walking directory:", process_directory)
    for dir_path, dir_names, file_names in os.walk(process_directory):
        for file in file_names:
            skip = False
            print ("[INFO] Checking file:", file)
            file_path, file_name, file_extension = getFilePathinfo(file)
            fullfile_path=os.path.join(dir_path, file)
            if file_extension in extensionsToProcess:
                files_to_process[fullfile_path] = emptyFiletoProcess(fullfile_path)
                stream_data, video_streams, audio_streams = getStreams(fullfile_path)
                files_to_process[fullfile_path]['stream_data'] = stream_data
                files_to_process[fullfile_path]['video_streams'] = video_streams
                files_to_process[fullfile_path]['audio_streams'] = audio_streams
                # If there is more then 1 or no video stream, or it's already in
                # hevc, don't process the file.
                if (len(files_to_process[fullfile_path]['video_streams']) != 1):
                    print ("[WARNING] Skipping as no, or more then one video stream found in:", file)
                    skip = True;
                elif files_to_process[fullfile_path]['video_streams'][0]['codec_name'] == 'hevc':
                    print("[INFO] Skipping file (already in hevc):", file)
                    skip = True;
            if skip:
                files_to_process.pop(fullfile_path)
            print ("[INFO] Found", fullfile_path, "to be processed.")

    print ("[INFO] found", len(files_to_process), "files to process.")

    # Process files individually for transcoding.
    for file, file_data in files_to_process.items():
        # Refresh the kwargs for each file.
        kwargs = initkwargs()
        # Get the video height and width and set approriate CRF value.
        width = int(file_data['video_streams'][0]['width'])
        height = int(file_data['video_streams'][0]['height'])
        kwargs['crf']=str(getCRF(height, width))
        # Check if we need to process DTS audio streams.
        if convertDTS:
            num_DTS = 0
            for audio in file_data['audio_streams']:
                if audio['codec_name'] == 'dts':
                    num_DTS += 1
                    # Set audio stream options for dts.
                    kwargs['c:a'] = 'eac3'
                    kwargs['b:a'] = '640k'
                    # If there is at least 1 DTS stream and at least one audio
                    # stream that isn't DTS throw a warning. As all will be
                    # converted?
                    # TODO: Test and transcode only the dts streams?
                    if len(audio) > num_DTS and num_DTS != 0:
                        print("[WARNING] DTS conversion to EAC flagged with more then one audio stream for file:", file)
        # Select all streams.
        kwargs['map']='0'
        # Convert the video stream to a x265 mkv.
        kwargs['c:v'] = 'libx265'
        kwargs['format']='matroska'
        # Prepare new file name and FFmpeg.
        file_data['converted_file'] = getNewFileName(file)
        # Execute FFmpeg
        for attempt in range(retryFailure):
            try:
                print("[INFO] Transcoding to file:", file_data['converted_file'])
                out, err = ( ffmpeg
                    .input(file)
                    .output(file_data['converted_file'], **kwargs)
                    .overwrite_output()
                    .run(capture_stdout=True, capture_stderr=True, quiet=True)
                )
            except ffmpeg.Error as e:
                # Uncomment for troubleshooting? I found `sudo dmesg` to be
                # better, particularly if ffmpeg is segfaulting.
                #print(e.stderr, file=sys.stderr)
                print ("[ERROR] ffmpeg error transcoding file:", file_data['converted_file'])
            else:
                break
        else:
            print ("[ERROR] ffmpeg transcoding failed after", retryFailure, "attempts for file:", file)
            file_data['failed'] = True
        print("[INFO] Transcoding completed for file:", file_data['converted_file'])

    # Check if files were processed successfully and move or clean them up.
    for file, file_data in files_to_process.items():
        # Remove failed files and clear the converted file name.
        # If ffmpeg failed and the new file exists, remove it.
        if file_data['failed'] and file_data['converted_file'] != "" and os.path.exists(file_data['converted_file']):
            os.remove(file_data['converted_file'])
            file_data['converted_file'] = ""
        # If ffmpeg was successful, remove the old file and replace it with the
        # new. Keeping the same modified and accessed dates.
        elif file_data['converted_file'] != "":
            # TODO: Find a better way to update just the stream size. Instead of
            # remuxing/copying the whole file with MKVToolNix.
            print("[INFO] Remuxing to update metadata for file:", file_data['converted_file'])
            tmp_mkv = getNewFileName(file_data['converted_file'])
            remux_mkv = MKVFile(file_data['converted_file'])
            remux_mkv.mux(tmp_mkv, silent=True)
            os.remove(file_data['converted_file'])
            os.rename(tmp_mkv, file_data['converted_file'])
            # Get the new video stream size.
            stream_data, video_streams, audio_streams = getStreams(file_data['converted_file'])
            new_vid_streams = video_streams
            old_size = int(file_data['video_streams'][0]['tags']['NUMBER_OF_BYTES'])
            new_size = int(new_vid_streams[0]['tags']['NUMBER_OF_BYTES'])
            # If the transcoded file is larger then the allowable max or smaller
            # then the minimum, delete it.
            if (new_size/old_size) > (maxPercent/100) or (new_size/old_size) < (minPercent/100):
                #percentage = str(new_size/old_size*100)
                print("[WARNING] Video is {:.2f}".format(new_size/old_size*100), "% of original and will be removed:", file_data['converted_file'])
                os.remove(file_data['converted_file'])
            else:
                # Maintain the file modifed and accessed dates.
                old_file_date = filedate.File(file)
                old_dates = old_file_date.get()
                new_file_date = filedate.File(file_data['converted_file'])
                new_dates = new_file_date.get()
                new_file_date.set(
                    created = new_dates['created'],
                    modified = old_dates['modified'],
                    accessed = old_dates['accessed']
                )
                # Move the new file in place.
                print("[INFO] Removing file:", file)
                os.remove(file)
                print("[INFO] Moving file:", file_data['converted_file'], "to: ", file)
                os.rename(file_data['converted_file'], file)


    sys.exit(POSTPROCESS_SUCCESS)
