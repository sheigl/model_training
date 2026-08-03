#!/bin/sh

BASE_DIR=/home/sheigl/code/model_training
PYTHON=$BASE_DIR/.venv/bin/python

cd $BASE_DIR
$PYTHON training_data/scrape_funtrivia.py "$@"
