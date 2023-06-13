# Video Encoding to RTSP Repository

This repository contains examples and code snippets showcasing various methods to encode video files into the RTSP (Real Time Streaming Protocol) format. RTSP is commonly used for streaming video and audio over the internet.

## Table of Contents

- [Video Encoding to RTSP Repository](#video-encoding-to-rtsp-repository)
  - [Table of Contents](#table-of-contents)
  - [Introduction](#introduction)
  - [Installation](#installation)
  - [Usage](#usage)
  - [Supported Video Formats](#supported-video-formats)
  - [Contributing](#contributing)
  - [License](#license)
  - [GPU decoding and encoding](#gpu-decoding-and-encoding)

## Introduction

The purpose of this repository is to provide developers with different approaches to encode video files into the RTSP format. Each method is implemented in a separate directory, containing the necessary code and instructions.

## Installation

To use the different video encoding methods, follow the instructions provided in each directory. Make sure you have the required dependencies installed and the appropriate hardware/software configurations, if any.

## Usage

Each encoding method has its own usage instructions within its respective directory. Please refer to the specific README files in each directory for detailed usage instructions.

## Supported Video Formats

This repository aims to support a wide range of video formats for encoding to RTSP. Some common video formats that can be used as input include:

- MP4
- AVI
- MOV
- MKV
- FLV
- WMV

Please note that the availability of video formats may vary depending on the specific encoding method used. Refer to the README files in each directory for details on the supported input video formats.

## Contributing

Contributions to this repository are welcome! If you have additional encoding methods, bug fixes, or improvements, feel free to open a pull request. Please follow the existing coding style and provide clear documentation for any changes made.

## License

The content of this repository is licensed under the [MIT License](LICENSE). You are free to use, modify, and distribute the code and examples provided. However, please note that any usage of third-party libraries or dependencies may be subject to their respective licenses.

## GPU decoding and encoding
bash```
gst-launch-1.0 filesrc location=dance.mp4 ! qtdemux ! h264parse ! nvv4l2decoder  ! nvvideoconvert ! queue !  nvv4l2h264enc ! rtph264pay ! queue name=stuttering_queue ! udpsink port=5000 host=127.0.0.1
```