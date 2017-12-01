sqlpylus
===================

sqlpylus is thin wrapper for sqlplus.
single Python script wrapped sqlplus.  


```python
import SqlPylus

conn = SqlPylus().connect('scott', 'tiger', 'localhost:1521/orcl')
cur = conn.cur()
for row in cur.execute('select empno, deptno from emp'):
    print(row['EMPNO'], row['DEPTNO'])
conn.close()
```

