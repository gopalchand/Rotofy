"""
rotify: Combine PNG or JPEG files in a folder into a movie file.
"""
# TODO - documentation based upon: https://www.datacamp.com/tutorial/docstrings-python

# # Python pre-requisites
# python v3.10 or higher
# pip install numpy
# pip install opencv-python

# External application pre-requisites:
# exiftool (https://exiftool.org/) and ffmpeg (https://ffmpeg.org/) must be installed
# The directories for these applications must be added to the PATH environment variable

import subprocess
import json
import os
import shutil
import errno
import sys
import argparse
import traceback
import glob
from datetime import datetime
import cv2

EXIF_TOOL_CMD = "exiftool.exe"
FFMPEG_CMD = "ffmpeg.exe"
DEFAULT_MOVIE_FILENAME = "output.mkv"
DEFAULT_BACKUP_DIR = "bak"

# Exit Errors
ERR_MISSING_DIR = 1001
ERR_INVALID_MOVIE_EXT = 1002
ERR_USUPPORTED_MOVIE_EXT = 1003
ERR_FRAMERATE_OUT_OF_RANGE = 1004
ERR_USER_EXIT = 1004
ERR_NO_PNG_FOR_JSON = 1005
ERR_RENAME_DUPLICATE = 1006
ERR_NO_JSON_FOR_ANNOTATE = 1007
ERR_NO_PNG_TO_CONVERT = 1008

# Message levels
MESSAGE_ERROR = 0
MESSAGE_INFO = 1
MESSAGE_WARN = 2
MESSAGE_DEBUG = 3

# Annotation defaults
TOP_BAR = 30
TEXT_OFFSET_X = 10
TEXT_OFFSET_Y = 20
TEXT_FONTSCALE = 0.4
TEXT_FONTFACE = cv2.FONT_HERSHEY_SIMPLEX

verbose_mode = False
input_dir = ""
output_dir = ""
rename_mode = False
skipjson_mode = False
keepjson_mode = False
annotate_mode = False
movie_file = ""
framerate_val = 0
overwritemovie_mode = False
skipmovie_mode =False

def log_message(level, message):
    """
    log_message(level, message)
    Display messages as follows:
    level = MESSAGE_ERROR: Error - always displayed
    level = MESSAGE_INFO: Information - always displayed
    level = MESSAGE_WARN: Warning - always displayed
    level = MESSAGE_DEBUG: Debug - displayed only if verbose_mode is True
    """

    # TODO - use stdout and stderr for messages
    if level is MESSAGE_DEBUG:
        if verbose_mode is True:
            print("DEBUG: " + message)
    elif level is MESSAGE_WARN:
        print("Warning: " +  message)
    elif level is MESSAGE_INFO:
        print(message)
    elif level is MESSAGE_ERROR:
        print("Error: " + message, file=sys.stderr)

def get_png_exif_tags(exif_file_path, exif_tags):
    """
    get_png_exif_tags(exif_path_file, exif_tags)
    return the EXIF tags defined in str list exif_tags
    """
    # TODO - add verbose logging for exiftool
    exiftool_cmd = [EXIF_TOOL_CMD, "-json"] + exif_tags + [exif_file_path]
    try:
        exif_data = subprocess.check_output(exiftool_cmd)
    except subprocess.CalledProcessError as exif_e:
        log_message(MESSAGE_ERROR, f"exiftool returned a non-zero exit status: {exif_e.returncode}")
        sys.exit(exif_e.returncode)  # Use a non-zero exit code to indicate an error

    exif_data_json = exif_data.decode('utf-8')
    return json.loads(exif_data_json)[0]

def sd_extract_parameters(sd_parameters_text):
    """
    sd_extract_parameters(sd_parameters_text)
    return the dict associated with the comma separated sd_parameters_text
    """
    sd_extracted_parameters = {}
    sd_key_mapping = {
        "Steps": "Steps",
        "Seed": "Seed",
        "CFG scale": "CFG scale",
        "Denoising strength": "Denoising strength"
    }
    for sd_line in sd_parameters_text.split(','):
        #pylint: disable=consider-using-dict-items
        for sd_key in sd_key_mapping:
            #pylint: enable=consider-using-dict-items
            if sd_key in sd_line:
                sd_value = sd_line.split(':')[1].strip()
                sd_extracted_parameters[sd_key_mapping[sd_key]] = sd_value
    return sd_extracted_parameters

def pb_show(pb_count, pb_total, pb_suffix):
    """
    pb_show(pb_count, pb_total, pb_suffix):
    Display progress bar using code from: https://www.geeksforgeeks.org/progress-bars-in-python/
    pb_count is the counter value
    pb_total is the total value
    pb_suffix is the suffix text e.g. count
    """
    pb_bar_length = 100
    pb_filled_up_length = int(round(pb_bar_length * pb_count / pb_total))
    pb_percentage = round(100.0 * pb_count / pb_total, 1)
    pb_bar = '=' * pb_filled_up_length + '-' * (pb_bar_length - pb_filled_up_length)
    #sys.stdout.write('[%s] %s%s ...%s\r' %(pb_bar, pb_percentage, '%', pb_suffix))
    sys.stdout.write(f'[{pb_bar}] {pb_percentage}% ...{pb_suffix}\r')
    sys.stdout.flush()

def main():
    # Outermost try
    try:
        # Validation
        if input_dir is not None:
            if os.path.exists(input_dir) is False:
                log_message(MESSAGE_ERROR, f"conversion directory {input_dir} does not exist")
                sys.exit(ERR_MISSING_DIR)  # Use a non-zero exit code to indicate an error

        # movie_file containers:
        # Recommended mp4|mkv => H.264 - MPEG-4 AVC (part 10)(avc1)
        # Not recommended - flv => (FLV1)
        # Not recommended - avi => MPEG-4 Video (FMP4) (non-H.264)
        # Not supported - mpg => ERROR: MPEG-1/2 does not support 5/1 fps

        if movie_file is not None:
            supported_movie_extensions = {'.mkv', '.mp4', '.flv', '.avi'}
            movie_file_name, movie_file_extension = os.path.splitext(movie_file)
            log_message(MESSAGE_DEBUG, f"Movie file extension = {movie_file_extension}")
            if movie_file_extension == "":
                log_message(MESSAGE_ERROR, f"invalid file extension for movie file:'{movie_file_extension}' \
    does not exist")
                sys.exit(ERR_INVALID_MOVIE_EXT)  # Use a non-zero exit code to indicate an error
            else:
                if str.lower(movie_file_extension) in supported_movie_extensions:
                    log_message(MESSAGE_INFO, f"supported extension for movie file:'{movie_file_extension}'")
                else:
                    log_message(MESSAGE_ERROR, f"unsupported extension for movie file:'{movie_file_extension}'")
                    sys.exit(ERR_USUPPORTED_MOVIE_EXT)  # Use a non-zero exit code to indicate an error

        if framerate_val is not None:
            if framerate_val < 1 or framerate_val > 30:
                log_message(MESSAGE_ERROR, f"frame rate value {framerate_val} is out of range 1..30")
                sys.exit(ERR_FRAMERATE_OUT_OF_RANGE)  # Use a non-zero exit code to indicate an error

        log_message(MESSAGE_DEBUG, f"verbose = {verbose_mode}")
        log_message(MESSAGE_DEBUG, f"conversion_directory = {input_dir}")
        log_message(MESSAGE_DEBUG, f"rename = {rename_mode}")
        log_message(MESSAGE_DEBUG, f"skip JSON = {skipjson_mode}")
        log_message(MESSAGE_DEBUG, f"keep JSON = {keepjson_mode}")
        log_message(MESSAGE_DEBUG, f"annotate = {annotate_mode}")
        log_message(MESSAGE_DEBUG, f"movie_file = {movie_file}")
        log_message(MESSAGE_DEBUG, f"frame rate = {framerate_val}")
        log_message(MESSAGE_DEBUG, f"overwritemovie_mode = {overwritemovie_mode}")
        log_message(MESSAGE_DEBUG, f"skip Movie = {skipmovie_mode}")

        # Path to the Input Pictures directory
        if input_dir is None:
            # Prompt the user and get input
            response = input("Warning: No directory specified using --dir. \
Are you sure you want to continue with current directory [Y/n]?")
            agree_list = {'yes', 'y', ''}
            if response.lower() in agree_list:
                input_directory_path = os.getcwd()  # Default to the current directory
            else:
                log_message(MESSAGE_ERROR, "Exiting program")
                sys.exit(ERR_USER_EXIT)  # Use a non-zero exit code to indicate an error
        else:
            input_directory_path = input_dir

        # Path to the Output Pictures directory
        # Use the input directory unless output_dir is used
        if output_dir is None:
            output_directory_path = input_directory_path
        else:
            output_directory_path = output_dir

        if skipjson_mode is False:
            # Iterate through the PNG files in the directory
            PNG_FILE_COUNT = len(glob.glob1(input_directory_path,"*.png"))
            if PNG_FILE_COUNT == 0:
                log_message(MESSAGE_ERROR, "Error no PNG files found (conversion may be required) \
    - exiting program")
                sys.exit(ERR_NO_PNG_FOR_JSON)  # Use a non-zero exit code to indicate an error

            log_message(MESSAGE_INFO, f"Creating JSON files from {PNG_FILE_COUNT} PNG files")
            if rename_mode is True:
                log_message(MESSAGE_INFO, "Also renaming PNG files using modified date")

            # pylint: disable=invalid-name
            json_create_count = 0
            # pylint: enable=invalid-name
            # Iterate through all files in the directory
            for filename in os.listdir(input_directory_path):
                if filename.endswith(".png"):
                    file_path = os.path.join(input_directory_path, filename)

                    # tags to be extracted
                    tags = ["-SourceFile", "-Datemodify", "-FileModifyDate", "-Parameters"]
                    png_tags = get_png_exif_tags(file_path, tags)
                    log_message(MESSAGE_DEBUG, f"EXIF tags read from file: {png_tags}")
                    source_file = png_tags.get('SourceFile')

                    # if the file has been modified by another application
                    modifydate_str = png_tags.get('Datemodify')
                    MODIFYDATE = None
                    if modifydate_str is not None:
                        log_message(MESSAGE_DEBUG, "datemodify found - using modify date")
                        MODIFYDATE = datetime.strptime(modifydate_str, "%Y-%m-%dT%H:%M:%S%z")
                    else:
                        log_message(MESSAGE_DEBUG, "datemodify is empty - falling back on File Modify Date")
                        modifydate_str = png_tags.get('FileModifyDate')
                        if modifydate_str is not None:
                            MODIFYDATE = datetime.strptime(modifydate_str, "%Y:%m:%d %H:%M:%S%z")
                    parameters = png_tags.get('Parameters')

                    log_message(MESSAGE_DEBUG, "EXIF extract")
                    log_message(MESSAGE_DEBUG, f"SourceFile = {source_file}")
                    log_message(MESSAGE_DEBUG, f"Modify Date = {MODIFYDATE}")
                    log_message(MESSAGE_DEBUG, f"parameters = {parameters}")

                    if source_file is None:
                        log_message(MESSAGE_DEBUG, f"Missing EXIF tag SourceFile using filename {filename}")

                        # TODO - testing required: this line was part of verbose output prior to change to log_message
                        source_file = filename

                    log_message(MESSAGE_DEBUG, "Attempting file rename based upon modify date")

                    # Extract the file extension from filename
                    file_name, file_extension = os.path.splitext(filename)

                    # default if rename is unsuccesful
                    new_filename = filename

                    if rename_mode is True:
                        # Rename the file using the formatted timestamp if datemodify exists
                        if MODIFYDATE is not None:
                            new_filename = MODIFYDATE.strftime("%y%m%d%H%M%S") + file_extension

                            if os.path.isfile(os.path.join(input_directory_path, new_filename)) is True:
                                log_message(MESSAGE_ERROR, f"Two files have the same modify dates:{MODIFYDATE} \
- perhaps --rename has already been used resulting in new modify dates - exiting")
                                sys.exit(ERR_RENAME_DUPLICATE)  # Use a non-zero exit code to indicate an error
                            else:

                                # delete existing backup
                                # TODO - if backup exists then save it with a different filename
                                # TODO - --no-backup option to avoid backup

                                # create the backup directory if necessary
                                backup_directory_path = os.path.join(input_directory_path, DEFAULT_BACKUP_DIR)
                                try:
                                    os.mkdir(backup_directory_path)
                                except OSError:
                                    if OSError.errno == errno.EEXIST:
                                        raise
                                    else:
                                        log_message(MESSAGE_DEBUG, \
f"backup file {backup_directory_path} exists (not an error)")
                                        pass

                                try:
                                    os.remove(os.path.join(backup_directory_path, filename))
                                    log_message(MESSAGE_DEBUG, \
f"existing backup file {os.path.join(backup_directory_path, filename)} successfully deleted")
                                except OSError:
                                    log_message(MESSAGE_DEBUG, \
f"backup file {os.path.join(backup_directory_path, filename)} \
not found (not an error)")
                                    pass

                                # save the backup
                                shutil.copy(os.path.join(input_directory_path, filename), \
os.path.join(backup_directory_path, filename))
                                log_message(MESSAGE_DEBUG, \
f"backup file {os.path.join(input_directory_path, filename)} created")

                                # rename PNG file
                                os.rename(os.path.join(input_directory_path, filename), \
os.path.join(input_directory_path, new_filename))
                            log_message(MESSAGE_DEBUG, \
f"file {os.path.join(input_directory_path, filename)} \
renamed to {os.path.join(input_directory_path, new_filename)}")
                        else:
                            log_message(MESSAGE_DEBUG, \
f"File {os.path.join(input_directory_path, new_filename)} \
does not have a date-based EXIF Tag to use - Not renaming")

                    # Extract the parameters from the text
                    if parameters is not None:
                        EXTRACTED_PARAMETERS = sd_extract_parameters(parameters)
                        log_message(MESSAGE_DEBUG, "The extracted parameters are:")
                        log_message(MESSAGE_DEBUG, f"{EXTRACTED_PARAMETERS}")
                    else:
                        log_message(MESSAGE_DEBUG, \
f"file {filename} does not have a Parameters EXIF Tag \
- Using default values")
                        EXTRACTED_PARAMETERS = 'None'

                    # Write Parameters to a text file with the same filename but with .txt extension
                    output_json_filename = os.path.splitext(new_filename)[0] + ".json"
                    with open(os.path.join(output_directory_path, output_json_filename), \
"w", -1, 'utf-8') as json_file:
                        json.dump(EXTRACTED_PARAMETERS, json_file, indent=4)
                        if verbose_mode is True:
                            log_message(MESSAGE_DEBUG, f"The Parameters have been written to: \
{os.path.join(output_directory_path, output_json_filename)}")
                        else:
                            json_create_count = json_create_count + 1
                            pb_show(json_create_count,PNG_FILE_COUNT, str(json_create_count))
                else:
                    log_message(MESSAGE_DEBUG, f"Skipping non-PNG file/directory {filename}")

        # Iterate through the PNG files in the directory
        PNG_FILE_COUNT = len(glob.glob1(input_directory_path,"*.png"))
        if PNG_FILE_COUNT == 0:
            log_message(MESSAGE_ERROR, "No PNG files found (conversion may be required)\
- exiting program")
            sys.exit(ERR_NO_PNG_TO_CONVERT)  # Use a non-zero exit code to indicate an error

        log_message(MESSAGE_INFO, f"\nStarting PNG conversion to JPEG of {PNG_FILE_COUNT} files")
        if annotate_mode is True:
            log_message(MESSAGE_INFO, "Also annotating JPEG files with data from JSON files.")

        # pylint: disable=invalid-name
        jpeg_create_count = 0
        # pylint: enable=invalid-name
        for png_file in sorted(os.listdir(input_directory_path)):
            if png_file.endswith(".png"):
                png_filename = os.path.splitext(png_file)[0]

                # Use OpenCV to convert file
                log_message(MESSAGE_DEBUG, f"Reading {input_directory_path + png_file}\
for conversion")
                image = cv2.imread(os.path.join(input_directory_path, f"{png_file}"))

                if annotate_mode is True:
                    log_message(MESSAGE_DEBUG, "preparing annotation")

                    json_file = os.path.join(input_directory_path, f"{png_filename}.json")
                    if os.path.exists(json_file):
                        with open(json_file, 'r', -1, 'utf-8') as f:
                            TEXT_TO_DRAW =''
                            json_data = json.load(f)
                            if json_data != 'None':
                                TEXT_TO_DRAW = f"{png_filename} | Steps {json_data['Steps']} | \
CFG {json_data['CFG scale']} | Seed {json_data['Seed']} | \
Denoise {json_data['Denoising strength']} |"
                            else:
                                TEXT_TO_DRAW = ""

                        log_message(MESSAGE_DEBUG, f"annotating file with {TEXT_TO_DRAW}")
                        height, width, channels = image.shape
                        image = cv2.rectangle(image, (0,0), (width, TOP_BAR), (0,0,0), -1)
                        image = cv2.putText(image, TEXT_TO_DRAW, (TEXT_OFFSET_X,TEXT_OFFSET_Y), \
fontScale = TEXT_FONTSCALE, fontFace = TEXT_FONTFACE, \
color = (255,255,255), thickness = 1, bottomLeftOrigin=False)
                    else:
                        log_message(MESSAGE_ERROR, f"Error: JSON file {json_file} not found. \
Perhaps --skipjson has been used without JSON file creation - exiting program")
                        sys.exit(ERR_NO_JSON_FOR_ANNOTATE)  \
                            # Use a non-zero exit code to indicate an error

                jpeg_file =os.path.splitext(png_file)[0] + ".jpg"
                cv2.imwrite(os.path.join(output_directory_path, f"{jpeg_file}"), image)
                if verbose_mode is True:
                    log_message(MESSAGE_DEBUG, f"\nJPEG file {output_directory_path + jpeg_file} \
saved")
                else:
                    jpeg_create_count = jpeg_create_count + 1
                    pb_show(jpeg_create_count,PNG_FILE_COUNT,str(jpeg_create_count))

        log_message(MESSAGE_INFO, "\nCreating Movie file")
        if framerate_val is True:
            log_message(MESSAGE_INFO, f"Also using frame rate of {framerate_val}")

        if movie_file is not None:
            OUTPUT_MOVIE_FILE = movie_file
            log_message(MESSAGE_INFO, f"Also using movie_file {OUTPUT_MOVIE_FILE}")
        else:
            OUTPUT_MOVIE_FILE = DEFAULT_MOVIE_FILENAME

        # Delete output file
        if os.path.isfile(os.path.join(output_directory_path, OUTPUT_MOVIE_FILE)):
            if overwritemovie_mode is True:
                log_message(MESSAGE_DEBUG, \
f"Deleting {os.path.join(output_directory_path, OUTPUT_MOVIE_FILE)}")
                os.remove(os.path.join(output_directory_path, OUTPUT_MOVIE_FILE))
            else:
                # Prompt the user and get input
                response = input \
(f"\nMovie file {os.path.join(output_directory_path, OUTPUT_MOVIE_FILE)} \
exists - use --overwritemovie to avoid in future. Delete [y/N]?")
                disagree_list = {'no', 'n', ''}
                if response.lower() in disagree_list:
                    log_message(MESSAGE_ERROR, "Exiting program")
                    sys.exit(ERR_USER_EXIT)  # Use a non-zero exit code to indicate an error
                else:
                    log_message(MESSAGE_DEBUG,\
f"deleting {os.path.join(output_directory_path, OUTPUT_MOVIE_FILE)}")
                    os.remove(os.path.join(output_directory_path, OUTPUT_MOVIE_FILE))

        # Call ffmpeg to create the movie
        # Appropriate level of logging based upon verbose_mode
        # no audio stream
        # frame rate is 1 Hz

        if verbose_mode is True:
            LOG_LEVEL = 'debug'
        else:
            LOG_LEVEL = 'panic'

        # This suffers from https://trac.ffmpeg.org/ticket/3164 - last frame is not vieweable
        # However the last frame is saved to the file as evidenced by, for example,
        # ffmpeg -r <framerate> -i file.mkv -r 1 mkv%03d.png

        if framerate_val is not None:
            log_message(MESSAGE_WARN, "Last frame of movie file may not be vieweable \
for non-default frame rates")
            ffmpeg_cmd_line = f'type {os.path.join(output_directory_path, "*.jpg")} | \
{FFMPEG_CMD} -loglevel {LOG_LEVEL} -framerate {framerate_val}  \
-an -f image2pipe -i - {os.path.join(output_directory_path, OUTPUT_MOVIE_FILE)}'
        else:
            ffmpeg_cmd_line = f'type {os.path.join(output_directory_path, "*.jpg")} | \
    {FFMPEG_CMD} -loglevel {LOG_LEVEL} -an -f image2pipe -i - \
    {os.path.join(output_directory_path, OUTPUT_MOVIE_FILE)}'

        log_message(MESSAGE_INFO, f"About to run '{ffmpeg_cmd_line}'")
        try:
            # TODO - remove output from ffmpeg
            completed_process = subprocess.run \
(ffmpeg_cmd_line, shell=True, capture_output=False, check=True)
            log_message(MESSAGE_INFO, f"Output file {OUTPUT_MOVIE_FILE} successfully created")
        except subprocess.CalledProcessError as e:
            log_message(MESSAGE_WARN, f"ffmpeg returned a non-zero exit status: {e.returncode} \
    - consider using --verbose")

        #tidy up
        if keepjson_mode is False:
            for json_file in sorted(os.listdir(output_directory_path)):
                if json_file.endswith(".json"):
                    json_filename = os.path.splitext(json_file)[0]
                    log_message(MESSAGE_DEBUG, f"Deleting file {output_directory_path + json_file}")
                    os.remove(os.path.join(output_directory_path, json_file))

    except Exception as e:
        log_message(MESSAGE_ERROR, \
f"Unhandled exception: {traceback.format_exception(*sys.exc_info())}")
        raise

if __name__ == '__main__':
    # Create a new ArgumentParser object
    parser = argparse.ArgumentParser \
(description='Combine PNG or JPEG files in a folder into an movie file. \n')

    # Add arguments
    parser.add_argument('--verbose', action='store_true', help='Verbose output')
    parser.add_argument('--input_dir', type=str, help='Directory to convert [Current Directory]')
    parser.add_argument('--output_dir', type=str, help='Directory to convert [Input Directory]')
    parser.add_argument('--rename', action='store_true', help='Rename files based upon EXIF tag')
    parser.add_argument('--skipjson', action='store_true', help='Skip JSON file creation')
    parser.add_argument('--keepjson', action='store_true', help='Do not remove json files after use')
    parser.add_argument('--annotate', action='store_true', help='Annotate top of JPEG files with key parameters')
    parser.add_argument('--moviefile', type=str, help='Output movie file mkv|mp4|avi|flv extensions supported')
    parser.add_argument('--framerate', type=int, help='Output movie frame rate')
    parser.add_argument('--overwritemovie', action='store_true', help='Overwrite movie file without prompting')
    parser.add_argument('--skipmovie', action='store_true', help='Skip Movie file creation')

    # Parse the arguments
    args = parser.parse_args()

    verbose_mode = args.verbose
    input_dir = args.input_dir
    output_dir = args.output_dir
    rename_mode = args.rename
    skipjson_mode = args.skipjson
    keepjson_mode = args.keepjson
    annotate_mode = args.annotate
    movie_file = args.moviefile
    framerate_val = args.framerate
    overwritemovie_mode = args.overwritemovie
    skipmovie_mode = args.skipmovie

    main()