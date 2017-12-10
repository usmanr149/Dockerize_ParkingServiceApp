FROM tiangolo/uwsgi-nginx:python3.5

MAINTAINER Sebastian Ramirez <tiangolo@gmail.com>

RUN pip install flask

# By default, allow unlimited file sizes, modify it to limit the file sizes
# To have a maximum of 1 MB (Nginx's default) change the line to:
# ENV NGINX_MAX_UPLOAD 1m
ENV NGINX_MAX_UPLOAD 0

#Install gcc
#FROM ubuntu:14.04
#RUN apt-get install -y build-essential wget

#Install the concorde app
WORKDIR /usr/src
RUN wget http://www.math.uwaterloo.ca/tsp/concorde/downloads/codes/src/co031219.tgz
RUN gunzip co031219.tgz 
RUN tar xvf co031219.tar
WORKDIR /usr/src/concorde
RUN ./configure
WORKDIR /usr/src/concorde/TSP
RUN make

# Set the concorde environment
ENV concorde /usr/src/concorde/TSP/concorde

# Install any needed packages specified in requirements.txt
WORKDIR /usr/src/app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# By default, Nginx listens on port 80.
# To modify this, change LISTEN_PORT environment variable.
# (in a Dockerfile or with an option for `docker run`)
ENV LISTEN_PORT 80

# Which uWSGI .ini file should be used, to make it customizable
ENV UWSGI_INI /app/uwsgi.ini

# URL under which static (not modified by Python) files will be requested
# They will be served by Nginx directly, without being handled by uWSGI
ENV STATIC_URL /static
# Absolute path in where the static files wil be
ENV STATIC_PATH /app/static

# If STATIC_INDEX is 1, serve / with /static/index.html directly (or the static URL configured)
# ENV STATIC_INDEX 1
ENV STATIC_INDEX 0

# Copy the entrypoint that will generate Nginx additional configs
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]


# Add demo app
COPY ./app /app
WORKDIR /app

CMD ["/usr/bin/supervisord"]