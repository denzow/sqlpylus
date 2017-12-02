# coding: utf-8
from __future__ import unicode_literals, print_function

import re
import os
import platform
import subprocess
try:
    from HTMLParser import HTMLParser
except ImportError:
    from html.parser import HTMLParser


def is_win():
    """
    Windowsかどうかでいくつか処理が異なるので判定用に設ける
    :return:
    """

    plat_form_name = platform.platform(aliased=1, terse=1)
    if "WIN" in plat_form_name.upper() and 'DARWIN' not in plat_form_name.upper():
        return True
    else:
        return False


class SqlPylusException(Exception):
    """
    custom exceptions
    """


class SqlplusHtmlResultParser(HTMLParser, object):
    """
    SQLPLUS -M HTML ON にした時の結果を取得する
    """
    def __init__(self, raw_string):
        super(SqlplusHtmlResultParser, self).__init__()
        self._raw_string = raw_string
        self._parsed_string = ''
        self._is_data = False
        self._last_tag = ''
        self._last_attrs = []
        self._tmp_result = []
        self._row_buffer = {
            'tag_name': '',
            'data': []
        }

    def handle_starttag(self, tag, attrs):
        """
        タグ発見時のアクション
        :param tag:
        :param attrs:
        :return:
        """
        # tableタグが始まったらデータ
        if tag.upper() == 'TABLE':
            self._is_data = True
        self._last_attrs = attrs
        self._last_tag = tag.upper()

    def handle_endtag(self, tag):
        """
        終了タグ発見時のアクション
        :param tag:
        :return:
        """
        # tableタグが終わったらデータも終わり
        if tag.upper() == 'TABLE':
            self._is_data = False
        if tag.upper() == 'TR':
            if self._row_buffer['tag_name'] in ('TD', 'TH'):
                self._tmp_result.append(self._row_buffer)
                self._row_buffer = {
                    'tag_name': '',
                    'attrs': [],
                    'data': []
                }
        self._last_tag = "/{0}".format(tag.upper())

    def handle_data(self, data):
        """
        タグ内のデータに対するアクション
        :param data:
        :return:
        """
        if self._is_data and self._last_tag.upper() in ('TD', 'TH'):
            self._row_buffer['tag_name'] = self._last_tag
            # 数字データの場合はalign=rightがtdタグに指定されている
            if ('align', 'right') in self._last_attrs:
                self._row_buffer['data'].append(float(data.strip()))
            else:
                self._row_buffer['data'].append(data.strip())

    def parse(self):
        """
        公開するインターフェース
        :return:
        """
        self.feed(self._raw_string)
        self.close()
        headers = [x['data'] for x in self._tmp_result if x['tag_name'] == 'TH']
        # 結果がない場合
        if len(headers) == 0:
            return []
        # pagesの関係で複数回HEADERが出るケースはあるが、先頭だけあれば良い
        header = headers[0]
        rows = [x['data'] for x in self._tmp_result if x['tag_name'] == 'TD']
        result_set = []

        for row in rows:
            result_set.append(dict(zip(header, row)))
        return result_set


class SqlPylusConnection(object):
    """
    connectionオブジェクトlikeなクラス。
    実質的にはsubprocess経由のSQL*Plusのラッパー
    """

    def __init__(self, sqlplus_binary_path, connect_info, password, environ):
        """

        :param sqlplus_binary_path: sqlplusのパス
        :param connect_info: 接続情報
        :param password: 接続時に指定したパスワード、マスキングする箇所の特定に使用
        :param environ: 環境変数のDict
        """
        self.sqlplus_path = sqlplus_binary_path
        self._connect_info = connect_info
        self.password = password
        self.environ = environ

        self._sql_plus_process = None

        self._connect()

    def __str__(self):

        return 'SqlPylusConnection({sqlplus} {connect})'.format(
            sqlplus=self.sqlplus_path,
            connect=self._connect_info.replace(self.password, 'XXXXX', 1)  # パスワード部分を置換する
        )

    def _get_encoding(self):
        """
        NLS_LANGからエンコーディングだけを取り出す
        結果をdecodeするために使用する
        :return:
        """
        nls_lang = self.environ.get('NLS_LANG')
        upper_encoding = nls_lang.split('.')[-1].upper()
        if 'UTF8' in upper_encoding:
            return 'utf-8'

        if 'SJIS' in upper_encoding:
            return 'sjis'

        if 'EUC' in upper_encoding:
            return 'euc-jp'

        return 'utf-8'

    def _is_sqlplus_alive(self):
        """
        SQLPLUS が生きているか
        :return:
        """
        if self._sql_plus_process and self._sql_plus_process.returncode is None:
            return True
        else:
            return False

    def close(self):
        """
        通常はないが、プロセスが残っている場合は終了させておく
        :return:
        """

        if self._is_sqlplus_alive():
            self._sql_plus_process.terminate()

    def execute(self, sql, timeout=None):
        """
        SQLを実行し、結果をDictで戻す
        :param sql:
        :param timeout:
        :rtype: dict
        :return:
        """
        if not self._is_sqlplus_alive():
            self._connect()

        # 末尾のカンマチェック
        if not sql.rstrip().endswith(';'):
            sql += ';'

        # 日付フォーマットをまともにしておく
        sql = 'ALTER SESSION SET NLS_DATE_FORMAT=\'yyyy-mm-dd hh24:mi:ss\';\n\n' + sql
        # エラー発生時に終了するようにさせておく
        sql = 'WHENEVER SQLERROR EXIT SQL.SQLCODE\n\n' + sql
        try:
            stdout, stderr = self._sql_plus_process.communicate(
                sql.encode(self._get_encoding()),
                timeout=timeout
            )
        except Exception as ex:
            # タイムアウト発生時は例外を送出
            raise SqlPylusException('TimedOut over[{timeout} second]'.format(timeout=timeout))

        # 正しくない終わり方
        if self._sql_plus_process.returncode != 0:
            stdout_text = ''
            stderr_text = ''

            if stderr:
                stderr_text = stderr.decode(self._get_encoding())
            if stdout:
                stdout_text = stdout.decode(self._get_encoding())

            whole_text = stderr_text.replace("\n", "") + stdout_text.replace("\n", "")
            if re.findall('(ORA|SP2|TNS)-(\d+)', whole_text):
                raise SqlPylusException('Execute Sql Error {0}'.format(
                    ['-'.join(x) for x in re.findall('(ORA|SP2|TNS)-(\d+)', whole_text)]
                ))
            else:
                raise SqlPylusException('Execute Sql Error {0}'.format(
                    stderr_text + stdout_text
                ))

        parser = SqlplusHtmlResultParser(stdout.decode(self._get_encoding()))
        result_set = parser.parse()

        return result_set

    def _connect(self):
        """
        SQLPLUSのプロセスを起動する
        :return:
        """
        sqlplus_execs = [self.sqlplus_path, '-S', '-L', '-M', 'HTML ON', self._connect_info]
        try:
            # winではclose_fdsがない
            if is_win():
                p = subprocess.Popen(
                    sqlplus_execs,
                    bufsize=1,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    env=self.environ
                )
            else:
                p = subprocess.Popen(
                    sqlplus_execs,
                    bufsize=1,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    close_fds=True,
                    env=self.environ
                )
        except Exception as e:
            raise SqlPylusException('connect failed. base error[{0}]'.format(e))
        self._sql_plus_process = p


class SqlPylus(object):

    def __init__(self, oracle_home=None, client_encoding='AL32UTF8'):
        """

        :param oracle_home: ORACLE_HOME,ここからSQLPLUSの場所を求める
        :param client_encoding: AL32UTF8等、NLS_LANGのエンコーディング部分(ロケールはAmerican_America固定
        """
        self.oracle_home = oracle_home or os.getenv('ORACLE_HOME')
        self.client_encoding = client_encoding
        self.environ = os.environ.copy()

        if not self.oracle_home:
            raise SqlPylusException('No OracleHome Settings.')

        # ORACLE_HOMEからsqlplusまでのパスを組み立てる
        if is_win():
            self.sqlplus_path = os.path.join(
                self.oracle_home,
                'bin',
                'sqlplus.exe'
            )
        else:
            self.sqlplus_path = os.path.join(
                self.oracle_home,
                'bin',
                'sqlplus'
            )
        # instant clientの場合はORACLE_HOME/binではない
        if not os.path.isfile(self.sqlplus_path):
            if is_win():
                self.sqlplus_path = os.path.join(
                    self.oracle_home,
                    'sqlplus.exe'
                )
            else:
                self.sqlplus_path = os.path.join(
                    self.oracle_home,
                    'sqlplus'
                )
        if not os.path.isfile(self.sqlplus_path):
            raise SqlPylusException('{0} is not a valid sqlplus path.'.format(self.sqlplus_path))

    def connect(self, user, password, dsn=None, oracle_sid=None, is_sysdba=False):
        """
        SqlPylusConnectionを生成し戻す

        :param user: DBユーザ名
        :param password: DBユーザパスワード
        :param dsn: リモート接続用の簡易接続文字列
        :param oracle_sid: ローカル接続の場合に使用するORACLE_SID
        :param is_sysdba: SYSDBA権限で接続するかどうか
        :return:
        """

        self.environ['ORACLE_HOME'] = self.oracle_home
        self.environ['NLS_LANG'] = 'American_America.{0}'.format(self.client_encoding)

        # 接続時に使用する文字列
        connect_info = '{user}/{password}'.format(
            user=user,
            password=password
        )

        if not dsn and not oracle_sid:
            raise SqlPylusException('No DSN or SID Settings.')

        if dsn and oracle_sid:
            raise SqlPylusException('DSN and SID Both are specified.')

        if dsn:
            connect_info += '@{0}'.format(dsn)

        if oracle_sid:
            self.environ['ORACLE_SID'] = oracle_sid

        if is_sysdba:
            connect_info += ' as sysdba'

        return SqlPylusConnection(
            sqlplus_binary_path=self.sqlplus_path,
            connect_info=connect_info,
            password=password,
            environ=self.environ
        )


if __name__ == '__main__':

    conn = SqlPylus().connect('scott', 'tiger', 'oralin:11204/v1124.world')
    print(conn)
    for row in conn.execute('select hiredate from emp;'):
        print(row)
