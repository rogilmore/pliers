from os.path import join, splitext
from .utils import get_test_data_path
from pliers.converters import memory, get_converter
from pliers.converters.video import (FrameSamplingConverter, 
                                        VideoToAudioConverter)
from pliers.converters.multistep import VideoToTextConverter
from pliers.converters.image import TesseractConverter, ImageToTextConverter
from pliers.converters.api import (WitTranscriptionConverter, 
                                        GoogleSpeechAPIConverter,
                                        IBMSpeechAPIConverter)
from pliers.converters.google import GoogleVisionAPITextConverter
from pliers.stimuli.video import VideoStim, VideoFrameStim, DerivedVideoStim
from pliers.stimuli.text import TextStim, ComplexTextStim
from pliers.stimuli.audio import AudioStim
from pliers.stimuli.image import ImageStim

import numpy as np
import math
import pytest
import os
import time


def test_video_to_audio_converter():
    filename = join(get_test_data_path(), 'video', 'small.mp4')
    video = VideoStim(filename)
    conv = VideoToAudioConverter()
    audio = conv.transform(video)
    assert audio.name == 'small.mp4_small.wav'
    assert splitext(video.filename)[0] == splitext(audio.filename)[0]
    assert np.isclose(video.duration, audio.duration, 1e-2)


def test_derived_video_converter():
    filename = join(get_test_data_path(), 'video', 'small.mp4')
    video = VideoStim(filename)
    assert video.fps == 30
    assert video.n_frames in (167, 168)
    assert video.width == 560

    # Test frame filters
    conv = FrameSamplingConverter(every=3)
    derived = conv.transform(video)
    assert len(derived.elements) == math.ceil(video.n_frames / 3.0)
    first = next(f for f in derived)
    assert type(first) == VideoFrameStim
    assert first.name == 'small.mp4_0'
    assert first.duration == 3 * (1 / 30.0)

    # Should refilter from original frames
    conv = FrameSamplingConverter(hertz=15)
    derived = conv.transform(derived)
    assert len(derived.elements) == math.ceil(video.n_frames / 6.0)
    first = next(f for f in derived)
    assert type(first) == VideoFrameStim
    assert first.duration == 3 * (1 / 15.0)

    # Test filter history
    assert derived.history.shape == (2, 3)
    assert np.array_equal(derived.history['filter'], ['every', 'hertz'])


def test_derived_video_converter_cv2():
    pytest.importorskip('cv2')
    filename = join(get_test_data_path(), 'video', 'small.mp4')
    video = VideoStim(filename)

    conv = FrameSamplingConverter(top_n=5)
    derived = conv.transform(video)
    assert len(derived.elements) == 5
    assert type(next(f for f in derived)) == VideoFrameStim


@pytest.mark.skipif("'WIT_AI_API_KEY' not in os.environ")
def test_witaiAPI_converter():
    audio_dir = join(get_test_data_path(), 'audio')
    stim = AudioStim(join(audio_dir, 'homer.wav'))
    conv = WitTranscriptionConverter()
    out_stim = conv.transform(stim)
    assert type(out_stim) == ComplexTextStim
    first_word = next(w for w in out_stim)
    assert type(first_word) == TextStim
    #assert '_' in first_word.name
    text = [elem.text for elem in out_stim]
    assert 'thermodynamics' in text or 'obey' in text


@pytest.mark.skipif("'GOOGLE_API_KEY' not in os.environ")
def test_googleAPI_converter():
    audio_dir = join(get_test_data_path(), 'audio')
    stim = AudioStim(join(audio_dir, 'homer.wav'))
    conv = GoogleSpeechAPIConverter()
    out_stim = conv.transform(stim)
    assert type(out_stim) == ComplexTextStim
    text = [elem.text for elem in out_stim]
    assert 'thermodynamics' in text or 'obey' in text


@pytest.mark.skipif("'IBM_USERNAME' not in os.environ or "
    "'IBM_PASSWORD' not in os.environ")
def test_ibmAPI_converter():
    audio_dir = join(get_test_data_path(), 'audio')
    stim = AudioStim(join(audio_dir, 'homer.wav'))
    conv = IBMSpeechAPIConverter()
    out_stim = conv.transform(stim)
    assert type(out_stim) == ComplexTextStim
    first_word = next(w for w in out_stim)
    assert type(first_word) == TextStim
    assert first_word.duration > 0
    assert first_word.onset != None

    full_text = [elem.text for elem in out_stim]
    assert 'thermodynamics' in full_text or 'obey' in full_text


def test_tesseract_converter():
    pytest.importorskip('pytesseract')
    image_dir = join(get_test_data_path(), 'image')
    stim = ImageStim(join(image_dir, 'button.jpg'))
    conv = TesseractConverter()
    out_stim = conv.transform(stim)
    assert out_stim.name == 'button.jpg_Exit'
    assert out_stim.text == 'Exit'


@pytest.mark.skipif("'GOOGLE_APPLICATION_CREDENTIALS' not in os.environ")
def test_google_vision_api_text_converter():
    conv = GoogleVisionAPITextConverter(num_retries=5)
    filename = join(get_test_data_path(), 'image', 'button.jpg')
    stim = ImageStim(filename)
    text = conv.transform(stim).text
    assert 'Exit' in text
    
    conv = GoogleVisionAPITextConverter(handle_annotations='concatenate')
    text = conv.transform(stim).text
    assert 'Exit' in text


def test_get_converter():
    conv = get_converter(ImageStim, TextStim)
    assert isinstance(conv, ImageToTextConverter)
    conv = get_converter(TextStim, ImageStim)
    assert conv is None


def test_converter_memoization():
    filename = join(get_test_data_path(), 'video', 'small.mp4')
    video = VideoStim(filename)
    conv = VideoToAudioConverter()

    from pliers.converters import cachedir
    memory.clear()

    # Time taken first time through
    start_time = time.time()
    audio1 = conv.convert(video)
    convert_time = time.time() - start_time
    cache_ts1 = conv.convert.timestamp

    start_time = time.time()
    audio2 = conv.convert(video)
    cache_time = time.time() - start_time
    cache_ts2 = conv.convert.timestamp

    # TODO: implement saner checking than this
    # Converting should be at least twice as slow as retrieving from cache
    assert convert_time >= cache_time * 2

    memory.clear()
    start_time = time.time()
    audio2 = conv.convert(video)
    cache_time = time.time() - start_time
    cache_ts2 = conv.convert.timestamp

    # After clearing the cache, checks should fail
    assert convert_time <= cache_time * 2


@pytest.mark.skipif("'WIT_AI_API_KEY' not in os.environ")
def test_multistep_converter():
    conv = VideoToTextConverter()
    filename = join(get_test_data_path(), 'video', 'obama_speech.mp4')
    stim = VideoStim(filename)
    text = conv.transform(stim)
    assert isinstance(text, ComplexTextStim)
    first_word = next(w for w in text)
    assert type(first_word) == TextStim