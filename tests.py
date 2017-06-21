#!/usr/bin/env python3

from unittest import TestCase, main
from unittest.mock import patch, MagicMock
from io import StringIO

class Qual:
  def __init__(self, name, op, value, is_list=False):
    self.field_name = name
    self.operator = op
    self.value = value
    self.is_list_operator = is_list

class ForeignDataWrapper:
  def __init__(self, options, columns):
    pass

class multicorn:
  ForeignDataWrapper = ForeignDataWrapper

import sys
sys.modules['multicorn'] = multicorn

from ttfkam import FindWrapper

ID_BUILTIN = 0
ID_PATTERN = 1
ID_EXECUTABLE = 2

TEST_DIR = '/usr/share/example/'
TEST_ARGS = ['/usr/bin/find', '-O3', '-L', TEST_DIR,
             '-regextype', 'posix-egrep', '-ignore_readdir_race']

class FindWrapperTests(TestCase):

  def test_root_with_slash(self):
    columns = { 'path': None, 'modified': None }
    fw = FindWrapper({ 'root_directory': '/dir/no/slash/' }, columns)
    self.assertEqual(fw._root, '/dir/no/slash/')

  def test_root_without_slash(self):
    columns = { 'path': None, 'modified': None }
    fw = FindWrapper({ 'root_directory': '/dir/no/slash' }, columns)
    self.assertEqual(fw._root, '/dir/no/slash/')

  @patch('ttfkam.Popen')
  @patch('ttfkam.PIPE')
  def test_basic(self, mock_pipe, mock_popen):
    process_mock = MagicMock()
    process_attrs = { 'stdout': StringIO('example.txt\t2017-03-22+22:33:15.3646792370\n') }
    process_mock.configure_mock(**process_attrs)
    mock_popen.return_value = process_mock
    columns = { 'path': None, 'modified': None }
    fw = FindWrapper({ 'root_directory': TEST_DIR }, columns)
    self.assertIn('path', fw._handlers)
    self.assertEqual(fw._handlers['path'][0], ID_BUILTIN)
    self.assertEqual(fw._handlers['path'][1], '%P')
    self.assertIn('modified', fw._handlers)
    self.assertEqual(fw._handlers['modified'][0], ID_BUILTIN)
    self.assertEqual(fw._handlers['modified'][1], '%T+')
    row = next(fw.execute([], columns))
    expected = TEST_ARGS + [ '-printf', '%P\t%T+\n' ]
    mock_popen.assert_called_with(expected, stdout=mock_pipe, universal_newlines=True)
    self.assertEqual(row, { 'modified': '2017-03-22 22:33:15.3646792370', 'path': 'example.txt' })

  @patch('ttfkam.Popen')
  @patch('ttfkam.PIPE')
  def test_multi(self, mock_pipe, mock_popen):
    process_mock = MagicMock()
    process_attrs = { 'stdout': StringIO('example1.txt\t2017-03-22+22:33:15.3646792370\n' +
                                         'example2.txt\t2017-03-22+22:33:45.3646792370\n') }
    process_mock.configure_mock(**process_attrs)
    mock_popen.return_value = process_mock
    columns = { 'path': None, 'modified': None }
    fw = FindWrapper({ 'root_directory': TEST_DIR }, columns)
    rows = fw.execute([], columns)
    row = next(rows)
    self.assertEqual(row, { 'modified': '2017-03-22 22:33:15.3646792370', 'path': 'example1.txt' })
    row = next(rows)
    self.assertEqual(row, { 'modified': '2017-03-22 22:33:45.3646792370', 'path': 'example2.txt' })

  @patch('ttfkam.Popen')
  @patch('ttfkam.PIPE')
  def test_exec(self, mock_pipe, mock_popen):
    process_mock = MagicMock()
    process_attrs = { 'stdout': StringIO('example.txt\t2017-03-22+22:33:15.3646792370\n' +
                                         'text/plain\n') }
    process_mock.configure_mock(**process_attrs)
    mock_popen.return_value = process_mock
    columns = { 'path': None, 'modified': None, 'mime_type': None }
    fw = FindWrapper({ 'root_directory': TEST_DIR,
                       'mime_type': '/usr/bin/file -b -i' }, columns)
    row = next(fw.execute([], columns))
    self.assertEqual(row, { 'modified': '2017-03-22 22:33:15.3646792370',
                            'path': 'example.txt',
                            'mime_type': 'text/plain' })
    expected = TEST_ARGS + [ '-printf', '%P\t%T+\n',
                             '-exec', '/usr/bin/file', '-b', '-i', '{}', ';' ]
    mock_popen.assert_called_with(expected, stdout=mock_pipe, universal_newlines=True)

  @patch('ttfkam.Popen')
  @patch('ttfkam.PIPE')
  def test_alias(self, mock_pipe, mock_popen):
    process_mock = MagicMock()
    process_attrs = { 'stdout': StringIO('example.txt\t2017-03-22+22:33:15.3646792370\n') }
    process_mock.configure_mock(**process_attrs)
    mock_popen.return_value = process_mock
    columns = { 'path': None, 'ts': None }
    fw = FindWrapper({ 'root_directory': TEST_DIR,
                       'ts': 'modified' }, columns)
    row = next(fw.execute([], columns))
    self.assertEqual(row, { 'ts': '2017-03-22 22:33:15.3646792370',
                            'path': 'example.txt' })
    expected = TEST_ARGS + [ '-printf', '%P\t%T+\n' ]
    mock_popen.assert_called_with(expected, stdout=mock_pipe, universal_newlines=True)

  @patch('ttfkam.Popen')
  @patch('ttfkam.PIPE')
  def test_quals(self, mock_pipe, mock_popen):
    process_mock = MagicMock()
    process_attrs = { 'stdout': StringIO('example.txt\n') }
    process_mock.configure_mock(**process_attrs)
    mock_popen.return_value = process_mock
    columns = { 'path': None, 'depth': None, 'type': None }
    fw = FindWrapper({ 'root_directory': TEST_DIR }, columns)
    row = next(fw.execute([Qual('depth','=',2), Qual('type','=','f')], { 'path': None }))
    self.assertEqual(row, { 'path': 'example.txt' })
    expected = TEST_ARGS + [ '-mindepth', '2', '-maxdepth', '2', '-type', 'f', '-printf', '%P\n' ]
    mock_popen.assert_called_with(expected, stdout=mock_pipe, universal_newlines=True)

  @patch('ttfkam.Popen')
  @patch('ttfkam.PIPE')
  def test_pattern(self, mock_pipe, mock_popen):
    process_mock = MagicMock()
    process_attrs = { 'stdout': StringIO('example.txt\n') }
    process_mock.configure_mock(**process_attrs)
    mock_popen.return_value = process_mock
    columns = { 'stem': None, 'extension': None }
    fw = FindWrapper({ 'root_directory': TEST_DIR,
                       'stem': '(?P<stem>[^.]+)\\.(?P<extension>[^.]+)' }, columns)
    row = next(fw.execute([], columns))
    self.assertEqual(row, { 'extension': 'txt', 'stem': 'example' })
    expected = TEST_ARGS + [ '-printf', '%P\n' ]
    mock_popen.assert_called_with(expected, stdout=mock_pipe, universal_newlines=True)

  @patch('ttfkam.Popen')
  @patch('ttfkam.PIPE')
  def test_anonymous_pattern(self, mock_pipe, mock_popen):
    process_mock = MagicMock()
    process_attrs = { 'stdout': StringIO('example.txt\n') }
    process_mock.configure_mock(**process_attrs)
    mock_popen.return_value = process_mock
    columns = { 'stem': None }
    fw = FindWrapper({ 'root_directory': TEST_DIR,
                       'stem': '([^.]+)\\.[^.]+' }, columns)
    row = next(fw.execute([], columns))
    self.assertEqual(row, { 'stem': 'example' })
    expected = TEST_ARGS + [ '-printf', '%P\n' ]
    mock_popen.assert_called_with(expected, stdout=mock_pipe, universal_newlines=True)

if __name__ == '__main__':
  main()
