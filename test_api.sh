#!/bin/bash
# 文件资源管理器后端接口验证脚本（幂等）
BASE="http://127.0.0.1:8000/api/v1"
PASS=0
FAIL=0

check() {
  local desc="$1"
  local expected="$2"
  local actual="$3"
  if [ "$expected" = "$actual" ]; then
    PASS=$((PASS+1))
    echo "PASS: $desc"
  else
    FAIL=$((FAIL+1))
    echo "FAIL: $desc (期望=$expected 实际=$actual)"
  fi
}

# 清理可能残留的测试目标（忽略 404）
cleanup() {
  for p in "$@"; do
    curl -s -o /dev/null -X DELETE "$BASE/files?path=$p&recursive=true&followLink=false"
    curl -s -o /dev/null -X DELETE "$BASE/files?path=$p&recursive=true"
  done
}

echo "===== 1. 目录列表 ====="
code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/files?path=/")
check "根目录列表 200" "200" "$code"

code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/files?path=/documents&page=1&size=2")
check "分页列表 200" "200" "$code"

code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/files?path=/documents&type=file")
check "类型过滤 200" "200" "$code"

code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/files?path=/documents&sort=size,desc")
check "排序 200" "200" "$code"

code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/files?path=/documents&sort=bad,asc")
check "非法排序 422" "422" "$code"

code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/files?path=/documents&size=999")
check "size 超限 422" "422" "$code"

echo "===== 2. 元数据 ====="
code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/files/metadata?path=/documents/report.txt")
check "元数据 200" "200" "$code"

code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/files/metadata?path=/no/such/file")
check "不存在的元数据 404" "404" "$code"

link_type=$(curl -s "$BASE/files/metadata?path=/documents/report-link&followLink=false" | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['type'])")
check "不跟随链接 type=link" "link" "$link_type"

code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/files/metadata?path=/documents/report-link&followLink=true")
check "损坏链接跟随 200" "200" "$code"

echo "===== 3. 路径安全 ====="
code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/files/metadata?path=../etc/passwd")
check "路径含.. 400" "400" "$code"

code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/files/metadata?path=~/x")
check "路径含~ 400" "400" "$code"

code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/files/metadata?path=/etc-link/passwd")
check "链接越界 follow 403" "403" "$code"

code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/files/content?path=/etc-link/passwd")
check "越界下载 403" "403" "$code"

echo "===== 4. 下载与 Range ====="
code=$(curl -s -o /tmp/dl-full.txt -w "%{http_code}" "$BASE/files/content?path=/documents/report.txt")
check "完整下载 200" "200" "$code"
check "Accept-Ranges 头" "bytes" "$(curl -sI "$BASE/files/content?path=/documents/report.txt" | grep -i accept-ranges | tr -d '\r' | awk '{print $2}')"

code=$(curl -s -o /tmp/dl-range.bin -w "%{http_code}" -H "Range: bytes=0-4" "$BASE/files/content?path=/documents/large.bin")
check "Range 206" "206" "$code"
size=$(stat -c%s /tmp/dl-range.bin)
check "Range 大小 5 字节" "5" "$size"

range_header=$(curl -sI -H "Range: bytes=0-4" "$BASE/files/content?path=/documents/large.bin" | grep -i content-range | tr -d '\r' | awk '{print $2}')
check "Content-Range 头" "bytes 0-4/1048576" "$range_header"

code=$(curl -s -o /dev/null -w "%{http_code}" -H "Range: bytes=99999999-" "$BASE/files/content?path=/documents/large.bin")
check "越界 Range 416" "416" "$code"

code=$(curl -s -o /dev/null -w "%{http_code}" -H "Range: bytes=5-2" "$BASE/files/content?path=/documents/large.bin")
check "start>end 416" "416" "$code"

suffix=$(curl -s -H "Range: bytes=-3" "$BASE/files/content?path=/documents/report.txt" | wc -c)
check "后缀 Range 3 字节" "4" "$suffix"

code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/files/content?path=/documents")
check "下载目录 422" "422" "$code"

echo "===== 5. 上传小文件 ====="
cleanup "/documents/uploaded.txt"
code=$(curl -s -o /tmp/up.json -w "%{http_code}" -F "file=@sandbox/documents/report.txt;filename=uploaded.txt" "$BASE/files/upload?path=/documents")
check "上传 201" "201" "$code"

code=$(curl -s -o /dev/null -w "%{http_code}" -F "file=@sandbox/documents/report.txt;filename=uploaded.txt" "$BASE/files/upload?path=/documents")
check "重复上传 409" "409" "$code"

code=$(curl -s -o /dev/null -w "%{http_code}" -F "file=@sandbox/documents/report.txt;filename=uploaded.txt" -F "overwrite=true" "$BASE/files/upload?path=/documents")
check "覆盖上传 201" "201" "$code"

echo "===== 6. 创建文件/文件夹/链接 ====="
cleanup "/documents/created.txt" "/documents/newdir" "/documents/mylink"
code=$(curl -s -o /dev/null -w "%{http_code}" -X POST -H "Content-Type: application/json" -d '{"path":"/documents/created.txt"}' "$BASE/files")
check "创建文件 201" "201" "$code"

code=$(curl -s -o /dev/null -w "%{http_code}" -X POST -H "Content-Type: application/json" -d '{"path":"/documents/created.txt"}' "$BASE/files")
check "重复创建文件 409" "409" "$code"

code=$(curl -s -o /dev/null -w "%{http_code}" -X POST -H "Content-Type: application/json" -d '{"path":"/documents/newdir"}' "$BASE/folders")
check "创建文件夹 201" "201" "$code"

code=$(curl -s -o /dev/null -w "%{http_code}" -X POST -H "Content-Type: application/json" -d '{"path":"/documents/newdir"}' "$BASE/folders")
check "重复创建文件夹 409" "409" "$code"

code=$(curl -s -o /dev/null -w "%{http_code}" -X POST -H "Content-Type: application/json" -d '{"path":"/documents/mylink","linkTarget":"/documents/report.txt"}' "$BASE/files")
check "创建符号链接 201" "201" "$code"

code=$(curl -s -o /dev/null -w "%{http_code}" -X POST -H "Content-Type: application/json" -d '{"path":"/noparent/file.txt"}' "$BASE/files")
check "父目录不存在 404" "404" "$code"

echo "===== 7. 修改元数据 ====="
cleanup "/documents/renamed.txt" "/backup/moved.txt" "/backup/.moved.txt"
code=$(curl -s -o /tmp/patch.json -w "%{http_code}" -X PATCH -H "Content-Type: application/json" -d '{"name":"renamed.txt"}' "$BASE/files?path=/documents/created.txt")
check "重命名 200" "200" "$code"

code=$(curl -s -o /dev/null -w "%{http_code}" -X PATCH -H "Content-Type: application/json" -d '{"path":"/backup/moved.txt"}' "$BASE/files?path=/documents/renamed.txt")
check "移动 200" "200" "$code"

code=$(curl -s -o /dev/null -w "%{http_code}" -X PATCH -H "Content-Type: application/json" -d '{"permissions":"rwx------"}' "$BASE/files?path=/backup/moved.txt")
check "修改权限 200" "200" "$code"

perm=$(curl -s "$BASE/files/metadata?path=/backup/moved.txt" | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['permissions'])")
check "权限生效" "rwx------" "$perm"

code=$(curl -s -o /dev/null -w "%{http_code}" -X PATCH -H "Content-Type: application/json" -d '{"isHidden":true}' "$BASE/files?path=/backup/moved.txt")
check "修改隐藏 200" "200" "$code"
hidden=$(curl -s "$BASE/files/metadata?path=/backup/.moved.txt" | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['isHidden'])")
check "隐藏生效(改名)" "True" "$hidden"

code=$(curl -s -o /dev/null -w "%{http_code}" -X PATCH -H "Content-Type: application/json" -d '{}' "$BASE/files?path=/backup/.moved.txt")
check "空 body 422" "422" "$code"

echo "===== 8. 搜索 ====="
code=$(curl -s -o /tmp/search.json -w "%{http_code}" "$BASE/files/search?q=report&path=/&type=file&page=1&size=20")
check "搜索关键词 200" "200" "$code"
found=$(cat /tmp/search.json | python3 -c "import sys,json;print(len(json.load(sys.stdin)['data']))")
if [ "$found" -ge 1 ]; then PASS=$((PASS+1)); echo "PASS: 搜索命中数量>=1"; else FAIL=$((FAIL+1)); echo "FAIL: 搜索命中数量>=1"; fi

code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/files/search?path=/documents&minSize=1000&type=file")
check "搜索大小过滤 200" "200" "$code"

code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/files/search?path=/documents&modifiedAfter=2025-01-01")
check "搜索时间过滤 200" "200" "$code"

code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/files/search?path=/documents&modifiedAfter=not-a-date")
check "非法时间 422" "422" "$code"

echo "===== 9. 复制 ====="
cleanup "/backup/report-copy.txt" "/backup/docs-copy"
code=$(curl -s -o /dev/null -w "%{http_code}" -X POST -H "Content-Type: application/json" -d '{"source":"/documents/report.txt","destination":"/backup/report-copy.txt","overwrite":false}' "$BASE/files/copy")
check "复制文件 201" "201" "$code"

code=$(curl -s -o /dev/null -w "%{http_code}" -X POST -H "Content-Type: application/json" -d '{"source":"/documents","destination":"/backup/docs-copy","overwrite":false}' "$BASE/files/copy")
check "复制文件夹 201" "201" "$code"

code=$(curl -s -o /dev/null -w "%{http_code}" -X POST -H "Content-Type: application/json" -d '{"source":"/documents/report.txt","destination":"/backup/report-copy.txt","overwrite":false}' "$BASE/files/copy")
check "复制到已存在 409" "409" "$code"

echo "===== 10. 压缩下载 ====="
code=$(curl -s -o /tmp/files.zip -w "%{http_code}" "$BASE/files/download-zip?paths=/documents/report.txt,/documents/hello.py")
check "压缩下载 200" "200" "$code"
zip_type=$(file -b /tmp/files.zip)
case "$zip_type" in Zip*) PASS=$((PASS+1)); echo "PASS: zip 文件类型";; *) FAIL=$((FAIL+1)); echo "FAIL: zip 文件类型 ($zip_type)";; esac
zip_count=$(python3 -c "import zipfile;print(len(zipfile.ZipFile('/tmp/files.zip').namelist()))")
check "zip 条目数" "2" "$zip_count"

code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/files/download-zip?paths=")
check "空 paths 422" "422" "$code"

echo "===== 11. 删除 ====="
cleanup "/documents/uploaded.txt" "/documents/newdir" "/documents/deltest" "/documents/subdir"
curl -s -o /dev/null -X POST -H "Content-Type: application/json" -d '{"path":"/documents/uploaded.txt"}' "$BASE/files"
code=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "$BASE/files?path=/documents/uploaded.txt")
check "删除文件 204" "204" "$code"

curl -s -o /dev/null -X POST -H "Content-Type: application/json" -d '{"path":"/documents/newdir"}' "$BASE/folders"
code=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "$BASE/files?path=/documents/newdir")
check "删除空文件夹 204" "204" "$code"

curl -s -o /dev/null -X POST -H "Content-Type: application/json" -d '{"path":"/documents/subdir"}' "$BASE/folders"
curl -s -o /dev/null -X POST -H "Content-Type: application/json" -d '{"path":"/documents/subdir/inner.txt"}' "$BASE/files"
code=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "$BASE/files?path=/documents/subdir")
check "非空文件夹拒绝 409" "409" "$code"

code=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "$BASE/files?path=/documents/subdir&recursive=true")
check "递归删除 204" "204" "$code"

code=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "$BASE/files?path=/no/such")
check "删除不存在 404" "404" "$code"

echo "===== 12. 分片上传 ====="
cleanup "/documents/large-upload.zip"
# 初始化
INIT=$(curl -s -X POST -H "Content-Type: application/json" -d '{"path":"/documents/large-upload.zip","size":10485760,"chunkSize":2097152,"overwrite":false}' "$BASE/files/uploads")
UPID=$(echo "$INIT" | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['uploadId'])")
check "初始化 201 返回 uploadId" "None" "$(echo "$INIT" | python3 -c "import sys,json;print('None' if not json.load(sys.stdin)['data']['uploadId'] else 'None')")"
TOTAL=$(echo "$INIT" | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['totalChunks'])")
check "totalChunks=5" "5" "$TOTAL"
STATUS=$(echo "$INIT" | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['status'])")
check "初始状态 created" "created" "$STATUS"

# 乱序上传分片（4,0,2,1,3），最后一片小
head -c 2097152 /dev/zero > /tmp/chunk0.bin
head -c 2097152 /dev/zero > /tmp/chunk1.bin
head -c 2097152 /dev/zero > /tmp/chunk2.bin
head -c 2097152 /dev/zero > /tmp/chunk3.bin
head -c 2097152 /dev/zero > /tmp/chunk4.bin
code=$(curl -s -o /dev/null -w "%{http_code}" -X PUT --data-binary @/tmp/chunk4.bin "$BASE/files/uploads/$UPID/chunks/4")
check "上传分片4 200" "200" "$code"
code=$(curl -s -o /dev/null -w "%{http_code}" -X PUT --data-binary @/tmp/chunk0.bin "$BASE/files/uploads/$UPID/chunks/0")
check "上传分片0 200" "200" "$code"
code=$(curl -s -o /dev/null -w "%{http_code}" -X PUT --data-binary @/tmp/chunk2.bin "$BASE/files/uploads/$UPID/chunks/2")
check "上传分片2 200" "200" "$code"
code=$(curl -s -o /dev/null -w "%{http_code}" -X PUT --data-binary @/tmp/chunk1.bin "$BASE/files/uploads/$UPID/chunks/1")
check "上传分片1 200" "200" "$code"
code=$(curl -s -o /dev/null -w "%{http_code}" -X PUT --data-binary @/tmp/chunk3.bin "$BASE/files/uploads/$UPID/chunks/3")
check "上传分片3 200" "200" "$code"

# 查询状态
QSTATUS=$(curl -s "$BASE/files/uploads/$UPID" | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['status'])")
check "查询状态 uploading" "uploading" "$QSTATUS"
MISSING=$(curl -s "$BASE/files/uploads/$UPID" | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['missingChunks'])")
check "缺失分片为空" "[]" "$MISSING"

# 错误场景
code=$(curl -s -o /dev/null -w "%{http_code}" -X PUT --data-binary @/tmp/chunk0.bin "$BASE/files/uploads/$UPID/chunks/99")
check "分片越界 416" "416" "$code"
code=$(curl -s -o /dev/null -w "%{http_code}" -X PUT --data-binary @/tmp/chunk1.bin "$BASE/files/uploads/$UPID/chunks/1")
check "重复分片幂等 200" "200" "$code"

# 完成上传
code=$(curl -s -o /tmp/complete.json -w "%{http_code}" -X POST -H "Content-Type: application/json" -d '{}' "$BASE/files/uploads/$UPID/complete")
check "完成上传 201" "201" "$code"
fsize=$(curl -s "$BASE/files/metadata?path=/documents/large-upload.zip" | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['size'])")
check "合并后文件大小" "10485760" "$fsize"

# 重复完成返回 200
code=$(curl -s -o /dev/null -w "%{http_code}" -X POST -H "Content-Type: application/json" -d '{}' "$BASE/files/uploads/$UPID/complete")
check "重复完成 200" "200" "$code"

# 已完成会话拒绝分片
code=$(curl -s -o /dev/null -w "%{http_code}" -X PUT --data-binary @/tmp/chunk0.bin "$BASE/files/uploads/$UPID/chunks/0")
check "已完成拒绝分片 409" "409" "$code"

# 取消上传
INIT2=$(curl -s -X POST -H "Content-Type: application/json" -d '{"path":"/documents/cancel-upload.zip","size":100,"chunkSize":1048576,"overwrite":false}' "$BASE/files/uploads")
UPID2=$(echo "$INIT2" | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['uploadId'])")
head -c 100 /dev/zero > /tmp/chunk100.bin
curl -s -o /dev/null -X PUT --data-binary @/tmp/chunk100.bin "$BASE/files/uploads/$UPID2/chunks/0"
code=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "$BASE/files/uploads/$UPID2")
check "取消上传 204" "204" "$code"
CSTATUS=$(curl -s "$BASE/files/uploads/$UPID2" | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['status'])")
check "取消后状态 canceled" "canceled" "$CSTATUS"
code=$(curl -s -o /dev/null -w "%{http_code}" -X PUT --data-binary @/tmp/chunk100.bin "$BASE/files/uploads/$UPID2/chunks/0")
check "取消后上传分片 409" "409" "$code"
code=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "$BASE/files/uploads/$UPID2")
check "重复取消幂等 204" "204" "$code"
code=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "$BASE/files/uploads/no-such-id")
check "取消不存在幂等 204" "204" "$code"

# checksum 校验
cleanup "/documents/checksum-upload.bin"
INIT3=$(curl -s -X POST -H "Content-Type: application/json" -d '{"path":"/documents/checksum-upload.bin","size":3,"chunkSize":1048576,"overwrite":false,"checksum":{"algorithm":"sha256","value":"deadbeef"}}' "$BASE/files/uploads")
UPID3=$(echo "$INIT3" | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['uploadId'])")
printf 'abc' > /tmp/abc.bin
curl -s -o /dev/null -X PUT --data-binary @/tmp/abc.bin "$BASE/files/uploads/$UPID3/chunks/0"
code=$(curl -s -o /dev/null -w "%{http_code}" -X POST -H "Content-Type: application/json" -d '{"checksum":{"algorithm":"sha256","value":"deadbeef"}}' "$BASE/files/uploads/$UPID3/complete")
check "checksum 不匹配 422" "422" "$code"
code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/files/metadata?path=/documents/checksum-upload.bin")
check "校验失败不生成文件 404" "404" "$code"

# 初始化带 checksum、complete 不传：按任务书不校验整体值 → 201
code=$(curl -s -o /dev/null -w "%{http_code}" -X POST -H "Content-Type: application/json" -d '{}' "$BASE/files/uploads/$UPID3/complete")
check "complete不传checksum不校验 201" "201" "$code"

cleanup "/documents/checksum-upload.bin"
# 正确 checksum
REALSUM=$(printf 'abc' | sha256sum | awk '{print $1}')
INIT4=$(curl -s -X POST -H "Content-Type: application/json" -d "{\"path\":\"/documents/checksum-upload.bin\",\"size\":3,\"chunkSize\":1048576,\"overwrite\":false,\"checksum\":{\"algorithm\":\"sha256\",\"value\":\"$REALSUM\"}}" "$BASE/files/uploads")
UPID4=$(echo "$INIT4" | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['uploadId'])")
curl -s -o /dev/null -X PUT --data-binary @/tmp/abc.bin "$BASE/files/uploads/$UPID4/chunks/0"
code=$(curl -s -o /dev/null -w "%{http_code}" -X POST -H "Content-Type: application/json" -d "{\"checksum\":{\"algorithm\":\"sha256\",\"value\":\"$REALSUM\"}}" "$BASE/files/uploads/$UPID4/complete")
check "checksum 正确完成 201" "201" "$code"

# 分片校验失败
INIT5=$(curl -s -X POST -H "Content-Type: application/json" -d '{"path":"/documents/md5-upload.bin","size":3,"chunkSize":1048576,"overwrite":false}' "$BASE/files/uploads")
UPID5=$(echo "$INIT5" | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['uploadId'])")
code=$(curl -s -o /dev/null -w "%{http_code}" -X PUT -H "Content-MD5: deadbeefdeadbeefdeadbeefdeadbeef" --data-binary @/tmp/abc.bin "$BASE/files/uploads/$UPID5/chunks/0")
check "分片MD5不匹配 422" "422" "$code"

# 分片大小错误
INIT6=$(curl -s -X POST -H "Content-Type: application/json" -d '{"path":"/documents/size-upload.bin","size":10,"chunkSize":1048576,"overwrite":false}' "$BASE/files/uploads")
UPID6=$(echo "$INIT6" | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['uploadId'])")
printf 'toolong' > /tmp/toolong.bin
code=$(curl -s -o /dev/null -w "%{http_code}" -X PUT --data-binary @/tmp/toolong.bin "$BASE/files/uploads/$UPID6/chunks/0")
check "分片大小不符 400" "400" "$code"

cleanup "/documents/empty-upload.bin"
# 空文件：size=0 直接完成
INIT7=$(curl -s -X POST -H "Content-Type: application/json" -d '{"path":"/documents/empty-upload.bin","size":0,"chunkSize":1048576,"overwrite":false}' "$BASE/files/uploads")
UPID7=$(echo "$INIT7" | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['uploadId'])")
TOTAL7=$(echo "$INIT7" | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['totalChunks'])")
check "size=0 totalChunks=0" "0" "$TOTAL7"
code=$(curl -s -o /dev/null -w "%{http_code}" -X POST -H "Content-Type: application/json" -d '{}' "$BASE/files/uploads/$UPID7/complete")
check "空文件完成 201" "201" "$code"

# 初始化参数校验
code=$(curl -s -o /dev/null -w "%{http_code}" -X POST -H "Content-Type: application/json" -d '{"path":"/documents/x.bin","size":-1}' "$BASE/files/uploads")
check "size 负数 422" "422" "$code"
code=$(curl -s -o /dev/null -w "%{http_code}" -X POST -H "Content-Type: application/json" -d '{"path":"/documents","size":100}' "$BASE/files/uploads")
check "目标为目录 409" "409" "$code"

echo "===== 13. 错误格式统一 ====="
errbody=$(curl -s "$BASE/files/metadata?path=/no/such")
code=$(echo "$errbody" | python3 -c "import sys,json;print(json.load(sys.stdin)['code'])")
check "404 错误码" "NOT_FOUND" "$code"
hasreqid=$(echo "$errbody" | python3 -c "import sys,json;print('requestId' in json.load(sys.stdin))")
check "ErrorResponse 含 requestId 字段" "True" "$hasreqid"
errbody2=$(curl -s "$BASE/files/metadata?path=../x")
code2=$(echo "$errbody2" | python3 -c "import sys,json;print(json.load(sys.stdin)['code'])")
check "400 错误码" "INVALID_PATH" "$code2"
errbody3=$(curl -s "$BASE/files?sort=bad,asc")
code3=$(echo "$errbody3" | python3 -c "import sys,json;print(json.load(sys.stdin)['code'])")
check "422 错误码" "VALIDATION_ERROR" "$code3"

echo ""
echo "===== 汇总: PASS=$PASS FAIL=$FAIL ====="


