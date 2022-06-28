import io
import os
import tarfile
from collections import OrderedDict
import tempfile
from os.path import isfile, join

from buildrunner import BuildRunner
from buildrunner.docker.runner import DockerRunner
from buildrunner.utils import ContainerLogger, ConsoleLogger
import pytest


@pytest.fixture(name="runner")
def fixture_setup_runner():
    image_config = DockerRunner.ImageConfig(
        'docker.io/ubuntu:19.04',
        pull_image=False,
    )
    runner = DockerRunner(
        image_config=image_config,
    )
    container_id = runner.start(working_dir="/root")

    yield runner

    runner.stop()


@pytest.fixture(name="tmp_dir_name")
def fixture_setup_tmp_dir_context():
    with tempfile.TemporaryDirectory() as tmp_dir_name:
        cwd = os.getcwd()
        os.chdir(tmp_dir_name)
        yield tmp_dir_name
        os.chdir(cwd)


def create_test_files_in_docker(drunner, cache_name, docker_path, num_of_test_files: int = 5) -> list:
    test_files = []

    for curr in range(1, num_of_test_files + 1):
        test_files.append(f"{cache_name}{curr}.txt")

    assert num_of_test_files != 0
    assert len(test_files) == num_of_test_files

    with io.StringIO() as my_stream:
        log = ConsoleLogger(
            "colorize_log",
            my_stream
        )
        for filename in test_files:
            drunner.run(f"mkdir -p {docker_path} &&"
                        f"cd {docker_path} && "
                        f"echo {filename} > {filename}",
                        console=None,
                        stream=True,
                        log=log,
                        workdir="/root/")

    return test_files


def setup_cache_test_files(tmp_dir_name: str, cache_name: str, num_files: int = 3) -> list:
    cwd = os.getcwd()
    os.chdir(tmp_dir_name)
    archive_file = f"{cache_name}.{BuildRunner.get_cache_archive_ext()}"
    test_files = []

    with tarfile.open(archive_file, "w") as tar:
        for i in range(0, num_files):
            filename = f"{cache_name}_file{i}.txt"
            test_files.append(filename)
            with open(filename, "w") as file:
                file.write(f"This is in {filename}")
            tar.add(filename)
            os.remove(filename)

    os.chdir(cwd)
    return test_files


def test_restore_cache_basic(runner, tmp_dir_name):
    """
    Tests basic restore cache functionality
    """
    # cache_name, test_files, tmp_dir_name = prep_cache_files_type1
    # with tempfile.TemporaryDirectory() as tmp_dir_name:
    cache_name = "my_cache"
    test_files = setup_cache_test_files(tmp_dir_name=tmp_dir_name,
                                        cache_name=cache_name,
                                        num_files=3)

    docker_path = "/root/cache"

    caches = OrderedDict()
    caches[f"{tmp_dir_name}/{cache_name}.{BuildRunner.get_cache_archive_ext()}"] = docker_path

    runner.restore_caches(caches)

    with io.StringIO() as my_stream:
        log = ConsoleLogger(
            "colorize_log",
            my_stream
        )
        runner.run(f"ls -1 {docker_path}",
                   console=None,
                   stream=True,
                   log=log,
                   workdir="/")

        my_stream.seek(0)
        output = my_stream.readlines()

        for file in test_files:
            assert f"{file}\n" in output


def test_restore_cache_no_cache(runner):
    """
    Tests restore cache when a match is not found
    """
    with tempfile.TemporaryDirectory() as tmp_dir_name:
        cache_name = "my_cache"
        test_files = setup_cache_test_files(tmp_dir_name=tmp_dir_name,
                                            cache_name=cache_name,
                                            num_files=3)
        docker_path = "/root/cache"

        caches = OrderedDict()
        caches[f"{tmp_dir_name}/{cache_name}-bogusname.{BuildRunner.get_cache_archive_ext()}"] = docker_path

        runner.restore_caches(caches)

        with io.StringIO() as my_stream:
            log = ConsoleLogger(
                "colorize_log",
                my_stream
            )
            runner.run(f"ls -1 {docker_path}",
                       console=None,
                       stream=True,
                       log=log,
                       workdir="/")

            my_stream.seek(0)
            output = my_stream.readlines()

            for file in test_files:
                assert f"{file}\n" not in output


def test_restore_cache_prefix_matching(runner, tmp_dir_name):
    """
    Tests restore cache when there is prefix matching
    """
    cache_name_checksum = "my-cache-4196e213ba325c876fa893d007c61397fbf1537d"
    test_files_checksum = setup_cache_test_files(tmp_dir_name=tmp_dir_name,
                                                 cache_name=cache_name_checksum,
                                                 num_files=3)

    cache_name = "my-cache"
    test_files = setup_cache_test_files(tmp_dir_name=tmp_dir_name,
                                        cache_name=cache_name,
                                        num_files=3)

    docker_path = "/root/cache"

    caches = OrderedDict()
    caches[f"{tmp_dir_name}/{cache_name_checksum}.{BuildRunner.get_cache_archive_ext()}"] = docker_path
    caches[f"{tmp_dir_name}/{cache_name}.{BuildRunner.get_cache_archive_ext()}"] = docker_path

    runner.restore_caches(caches)

    with io.StringIO() as my_stream:
        log = ConsoleLogger(
            "colorize_log",
            my_stream
        )
        runner.run(f"ls -1 {docker_path}",
                   console=None,
                   stream=True,
                   log=log,
                   workdir="/")

        my_stream.seek(0)
        output = my_stream.readlines()

        for file in test_files:
            assert f"{file}\n" not in output

        for file in test_files_checksum:
            assert f"{file}\n" in output


def test_restore_cache_prefix_timestamps(runner, tmp_dir_name):
    """
    Tests that when the cache prefix matches it chooses the most recent archive file
    """
    docker_path = "/root/cache"
    cache_name_prefix = "my-cache-prefix-"
    cache_name_oldest = f"{cache_name_prefix}oldest"
    cache_name_middle = f"{cache_name_prefix}middle"
    cache_name_newest = f"{cache_name_prefix}newest"

    test_files_oldest = setup_cache_test_files(tmp_dir_name=tmp_dir_name,
                                               cache_name=cache_name_oldest,
                                               num_files=3)
    test_files_middle = setup_cache_test_files(tmp_dir_name=tmp_dir_name,
                                               cache_name=cache_name_middle,
                                               num_files=3)
    test_files_newest = setup_cache_test_files(tmp_dir_name=tmp_dir_name,
                                               cache_name=cache_name_newest,
                                               num_files=3)

    caches = OrderedDict()
    caches[f"{tmp_dir_name}/{cache_name_prefix}.{BuildRunner.get_cache_archive_ext()}"] = docker_path

    runner.restore_caches(caches)

    with io.StringIO() as my_stream:
        log = ConsoleLogger(
            "colorize_log",
            my_stream
        )
        runner.run(f"ls -1 {docker_path}",
                   console=None,
                   stream=True,
                   log=log,
                   workdir="/")

        my_stream.seek(0)
        output = my_stream.readlines()

        for file in test_files_oldest:
            assert f"{file}\n" not in output

        for file in test_files_middle:
            assert f"{file}\n" not in output

        for file in test_files_newest:
            assert f"{file}\n" in output


def test_save_cache_basic(runner, tmp_dir_name):
    """
    Test basic save cache functionality
    """
    cache_name = "my-cache"
    docker_path = "/root/cache"
    test_files = create_test_files_in_docker(drunner=runner,
                                             cache_name=cache_name,
                                             docker_path=docker_path,
                                             num_of_test_files=10)

    caches = OrderedDict()
    tarfile_name = f"{cache_name}.{BuildRunner.get_cache_archive_ext()}"
    caches[f"{tmp_dir_name}/{cache_name}.{BuildRunner.get_cache_archive_ext()}"] = docker_path
    runner.save_caches(caches)

    files = [f for f in os.listdir(tmp_dir_name) if isfile(join(tmp_dir_name, f))]
    assert tarfile_name in files

    extracted_dir = "extracted_data"
    os.mkdir(extracted_dir)
    with tarfile.open(tarfile_name) as tar:
        tar.extractall(extracted_dir)
        extracted_files = os.listdir(extracted_dir)

        assert len(test_files) == len(extracted_files)
        for file in test_files:
            assert file in extracted_files


def test_save_cache_multiple_cache_keys(runner, tmp_dir_name):
    """
    Test save cache functionality when there are multiple cache keys.
    At the time of this writing it should take the topmost cache key

    Example:
        caches:
        /root/.m2/repository:
          - venv-{{ checksum(["requirements.txt",]) }}
          - venv-

        This should result in the files under /root/.m2/repository  on the docker to
        be stored to  venv-<checksum>.{BuildRunner.get_cache_archive_ext()} on the host system
    """
    cache_name = "my-cache"
    cache_name_venv = "venv"
    cache_name_maven = "maven"
    docker_path = "/root/cache"
    test_files = create_test_files_in_docker(drunner=runner,
                                             cache_name=cache_name,
                                             docker_path=docker_path,
                                             num_of_test_files=5)

    caches = OrderedDict()
    tarfile_name = f"{cache_name}.{BuildRunner.get_cache_archive_ext()}"

    caches[f"{tmp_dir_name}/{cache_name}.{BuildRunner.get_cache_archive_ext()}"] = docker_path
    caches[f"{tmp_dir_name}/{cache_name_venv}.{BuildRunner.get_cache_archive_ext()}"] = docker_path
    caches[f"{tmp_dir_name}/{cache_name_maven}.{BuildRunner.get_cache_archive_ext()}"] = docker_path
    runner.save_caches(caches)

    files = [f for f in os.listdir(tmp_dir_name) if isfile(join(tmp_dir_name, f))]
    assert tarfile_name in files
    assert cache_name_venv not in files
    assert cache_name_maven not in files

    extracted_dir = "extracted_data"
    os.mkdir(extracted_dir)
    with tarfile.open(tarfile_name) as tar:
        tar.extractall(extracted_dir)
        extracted_files = os.listdir(extracted_dir)

        assert len(test_files) == len(extracted_files)
        for file in test_files:
            assert file in extracted_files

    # Change order of cache keys which on
    caches.clear()
    tarfile_name = f"{cache_name_venv}.{BuildRunner.get_cache_archive_ext()}"

    caches[f"{tmp_dir_name}/{cache_name_venv}.{BuildRunner.get_cache_archive_ext()}"] = docker_path
    caches[f"{tmp_dir_name}/{cache_name}.{BuildRunner.get_cache_archive_ext()}"] = docker_path
    caches[f"{tmp_dir_name}/{cache_name_maven}.{BuildRunner.get_cache_archive_ext()}"] = docker_path
    runner.save_caches(caches)

    files = [f for f in os.listdir(tmp_dir_name) if isfile(join(tmp_dir_name, f))]
    assert cache_name not in files
    assert tarfile_name in files
    assert cache_name_maven not in files

    extracted_dir = "extracted_data2"
    os.mkdir(extracted_dir)
    with tarfile.open(tarfile_name) as tar:
        tar.extractall(extracted_dir)
        extracted_files = os.listdir(extracted_dir)

        assert len(test_files) == len(extracted_files)
        for file in test_files:
            assert file in extracted_files


def test_save_cache_multiple_caches(runner, tmp_dir_name):
    venv_cache_name = "venv"
    venv_docker_path = "/root/venv_cache"
    venv_tarfile_name = f"{venv_cache_name}.{BuildRunner.get_cache_archive_ext()}"
    venv_extracted_dir = "venv_extracted_data"
    venv_test_files = create_test_files_in_docker(drunner=runner,
                                                  cache_name=venv_cache_name,
                                                  docker_path=venv_docker_path,
                                                  num_of_test_files=5)

    maven_cache_name = "maven"
    maven_docker_path = "/root/maven_cache"
    maven_tarfile_name = f"{maven_cache_name}.tar"
    maven_extracted_dir = "maven_extracted_data"
    maven_test_files = create_test_files_in_docker(drunner=runner,
                                                   cache_name=maven_cache_name,
                                                   docker_path=maven_docker_path,
                                                   num_of_test_files=5)

    caches = OrderedDict()

    caches[f"{tmp_dir_name}/{venv_cache_name}.{BuildRunner.get_cache_archive_ext()}"] = venv_docker_path
    caches[f"{tmp_dir_name}/{maven_cache_name}.{BuildRunner.get_cache_archive_ext()}"] = maven_docker_path
    runner.save_caches(caches)

    files = [f for f in os.listdir(tmp_dir_name) if isfile(join(tmp_dir_name, f))]
    assert venv_tarfile_name in files
    assert maven_tarfile_name in files

    os.mkdir(venv_extracted_dir)
    with tarfile.open(venv_tarfile_name) as tar:
        tar.extractall(venv_extracted_dir)
        extracted_files = os.listdir(venv_extracted_dir)

        assert len(venv_test_files) == len(extracted_files)
        for file in venv_test_files:
            assert file in extracted_files
        for file in maven_test_files:
            assert file not in extracted_files

    os.mkdir(maven_extracted_dir)
    with tarfile.open(maven_tarfile_name) as tar:
        tar.extractall(maven_extracted_dir)
        extracted_files = os.listdir(maven_extracted_dir)

        assert len(maven_test_files) == len(extracted_files)
        for file in venv_test_files:
            assert file not in extracted_files
        for file in maven_test_files:
            assert file in extracted_files
