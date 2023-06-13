FROM nvcr.io/nvidia/tensorflow:21.08-tf2-py3
RUN apt-get update

# Add open GL libraries
RUN apt-get update && \
        DEBIAN_FRONTEND=noninteractive  apt-get install -y --no-install-recommends \
        pkg-config \
        libglvnd-dev \
        libgl1-mesa-dev \
        libegl1-mesa-dev \
        libgles2-mesa-dev

RUN apt-get update && \
        DEBIAN_FRONTEND=noninteractive  apt-get install -y \
        wget \
        libyaml-cpp-dev \
        gnutls-bin

RUN apt-get update && \
        DEBIAN_FRONTEND=noninteractive         apt-get install -y --no-install-recommends \
        linux-libc-dev \
        libglew2.1 libssl1.1 libjpeg8 libjson-glib-1.0-0 \
        gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-tools gstreamer1.0-libav \
        gstreamer1.0-alsa \
        libcurl4 \
        libuuid1 \
        libjansson4 \
        libjansson-dev \
        librabbitmq4 \
        libgles2-mesa \
        libgstrtspserver-1.0-0 \
        libv4l-dev \
        gdb bash-completion libboost-dev \
        uuid-dev libgstrtspserver-1.0-0 libgstrtspserver-1.0-0-dbg libgstrtspserver-1.0-dev \
        libgstreamer1.0-dev \
        libgstreamer-plugins-base1.0-dev \
        libglew-dev \
        libssl-dev \
        libopencv-dev \
        freeglut3-dev \
        libjpeg-dev \
        libcurl4-gnutls-dev \
        libjson-glib-dev \
        libboost-dev \
        librabbitmq-dev \
        libgles2-mesa-dev \
        pkg-config \
        libxau-dev \
        libxdmcp-dev \
        libxcb1-dev \
        libxext-dev \
        libx11-dev \
        libnss3 \
        linux-libc-dev \
        git \
        wget \
        gnutls-bin \
        sshfs \
        python3-distutils \
        python3-apt \
        python \
        rsyslog \
        vim  rsync \
        gstreamer1.0-rtsp 


RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    libx11-xcb-dev \
    libxkbcommon-dev \
    libwayland-dev \
    libxrandr-dev \
    libegl1-mesa-dev && \
    rm -rf /var/lib/apt/lists/*

# Install DeepStreamSDK using debian package. DeepStream tar package can also be installed in a similar manner
RUN wget \
  --no-verbose --show-progress \
  --progress=bar:force:noscroll \
  -O /tmp/deepstream-6.0_6.0.0-1_amd64.deb \
  https://developer.download.nvidia.com/assets/Deepstream/DeepStream_6.0/deepstream-6.0_6.0.0-1_amd64.deb?t=eyJscyI6ImdzZW8iLCJsc2QiOiJodHRwczovL3d3dy5nb29nbGUuY29tLyJ9 \
  && DEBIAN_FRONTEND=noninteractive  apt-get install -y --no-install-recommends \
      /tmp/deepstream-6.0_6.0.0-1_amd64.deb

# WORKDIR /opt/nvidia/deepstream/deepstream

RUN ln -s /usr/lib/x86_64-linux-gnu/libnvcuvid.so.1 /usr/lib/x86_64-linux-gnu/libnvcuvid.so
RUN ln -s /usr/lib/x86_64-linux-gnu/libnvidia-encode.so.1 /usr/lib/x86_64-linux-gnu/libnvidia-encode.so

# To get video driver libraries at runtime (libnvidia-encode.so/libnvcuvid.so)
ENV NVIDIA_DRIVER_CAPABILITIES $NVIDIA_DRIVER_CAPABILITIES,video,compute,graphics,utility

RUN apt-get update &&  apt-get install -y libgstreamer1.0-dev \
    libgstreamer-plugins-base1.0-dev \
    libgstreamer-plugins-bad1.0-dev \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly \
    gstreamer1.0-libav \
    gstreamer1.0-tools \
    gstreamer1.0-x \
    gstreamer1.0-alsa gstreamer1.0-gl \
    gstreamer1.0-gtk3 gstreamer1.0-qt5 \
    gstreamer1.0-pulseaudio \
    gir1.2-gst-rtsp-server-1.0

RUN apt-get install -y libgstreamer1.0-dev \
    libgstreamer-plugins-base1.0-dev

RUN apt-get install -y \
    build-essential \
    cmake \
    gir1.2-gst-rtsp-server-1.0 \
    gtk-doc-tools \
    libtool \
    git \
    libssl-dev \
    unzip \
    autoconf \
    autopoint \
    glib-2.0 \
    libgtk2.0-dev \
    libglib2.0-dev \
    python3-gi \
    python3-tk \
    iputils-ping

RUN python3 -m pip install opencv-python
RUN python3 -m pip install --force-reinstall notebook
RUN python3 -m pip install --force-reinstall cryptography
RUN python3 -m pip install --force-reinstall Pillow
RUN python3 -m pip install nvidia-ml-py3
RUN python3 -m pip install tabulate
RUN python3 -m pip install memory-profiler
RUN python3 -m pip install docker



RUN mkdir /home/gstreamer
COPY Video_Codec_SDK_12.0.16.zip /home/gstreamer/
COPY install_video_codec_sdk.sh /home/gstreamer/
RUN chmod +x /home/gstreamer/install_video_codec_sdk.sh
RUN cd /home/gstreamer && ./install_video_codec_sdk.sh