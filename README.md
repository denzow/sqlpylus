sqlpylus
===================

sqlpylus はPython経由でOracleDatabaseにSQLを発行できるモジュールです。内部的にはSQLPLUSを起動し、その結果を標準出力経由で受け取って加工しています。
  

```python
import SqlPylus

conn = SqlPylus().connect('scott', 'tiger', 'localhost:1521/orcl')
for row in conn.execute('select empno, deptno from emp'):
    print(row['EMPNO'], row['DEPTNO'])
conn.close()
```

単一のPythonファイルで利用可能になっているため、OracleDatabaseにSQLを発行したいプロジェクト内に配置するだけで利用可能になります。

動作要件
-------------

以下の環境で利用可能です。

* Python 2.6~, Python 3.3~

なお、実行するには実行環境でSQLPLUSが利用できる状態である必要があります。instant Clientでも問題はありません。


導入方法
------------

`sqlpylus.sqlpylus.py`を任意のディレクトリにコピーします。そのうちpipに対応する予定です。

```
$ curl -o sqlpylus.py  https://raw.githubusercontent.com/denzow/sqlpylus/master/sqlpylus/sqlpylus.py
```

利用方法
-----------


### SqlPylus

接続等の起点になるクラスです。

```python

class SqlPylus(object):

    def __init__(self, oracle_home=None, client_encoding='AL32UTF8'):
        """

        :param oracle_home: ORACLE_HOME,ここからSQLPLUSの場所を求める
        :param client_encoding: AL32UTF8等、NLS_LANGのエンコーディング部分(ロケールはAmerican_America固定
        """
```

`oracle_home`と`client_encoding`を指定します。`oracle_home`は省略した場合ORACLE_HOME環境変数から取得します。

### SqlPylus().connect()

`SqlPylus`を初期化したら`connect`を実行しDBインスタンスとの接続を行います。

```python
conn = SqlPylus().connect(user='scott', password='tiger', dsn='localhost:1521/orcl')
```

接続情報等をここで指定します。

```python
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
```

指定した内容は`sqlplus {user}/{password}@{dsn}`としてSQLPLUSの起動に引き渡されます。
また`dsn`を指定せず、`oracle_sid`を指定した場合は`ORACLE_SID`環境変数として設定し、ローカル接続を試みます。

必要な情報を受け取った上で`SqlPylusConnection`を戻します。

### SqlPylusConnection

SQLPLUSをラップしています。実質的には `execute()`のみが利用可能です。

```python
    def execute(self, sql, timeout=None):
        """
        SQLを実行し、結果をDictで戻す
        :param sql:
        :param timeout:
        :rtype: dict
        :return:
        """
```


```python
for row in conn.execute('select ename, empno from emp'):
    print(row['ENAME'], row['EMPNO'])
```

sql文を引数にとり、戻された結果について各行をDict形式にしたListで戻します。Number型の列は自動でPythonのFloatにキャストされます。

制限事項
------------

* 現状SQL発行ごとにSQLPLUSで再接続するため複数のSQLでのトランザクションは管理できません
* SQLPLUSから戻された結果をすべて受け取ってからパースしているので、大量データを戻すSQLではパフォーマンスがかなり下がります
* Windowsの動作確認が不十分です