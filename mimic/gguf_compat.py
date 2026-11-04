"""Metadata-only adaptation of verified Ollama-format EmbeddingGemma GGUF.
Based on architecture/tensor mappings documented by Ollama's MIT-licensed
llama/compat/llama-ollama-compat.cpp. Tensor bytes are copied unchanged.
No Ollama executable, service, or Python model runtime is used for inference.
"""
import json
import os
from pathlib import Path
import shutil
import struct

SIZES={0:1,1:1,2:2,3:2,4:4,5:4,6:4,7:1,10:8,11:8,12:8}


def u32(file):return struct.unpack('<I',file.read(4))[0]
def u64(file):return struct.unpack('<Q',file.read(8))[0]
def string(file):return file.read(u64(file)).decode('utf-8')
def encoded(text):
    raw=text.encode();return struct.pack('<Q',len(raw))+raw


def skip(file,kind):
    if kind in SIZES:file.seek(SIZES[kind],1)
    elif kind==8:file.seek(u64(file),1)
    elif kind==9:
        subtype=u32(file);count=u64(file)
        if subtype in SIZES:file.seek(count*SIZES[subtype],1)
        else:
            for _ in range(count):skip(file,subtype)
    else:raise ValueError('Неизвестный тип метаданных GGUF')


def convert_embedding(source,target):
    source,target=Path(source),Path(target)
    temporary=target.with_suffix('.tmp')
    try:
        with open(source,'rb') as file:
            magic=file.read(4);version=u32(file);tensors=u64(file);entries=u64(file)
            if magic!=b'GGUF' or version!=3:raise ValueError('Неподдерживаемый GGUF')
            metadata={}
            for _ in range(entries):
                key=string(file);kind=u32(file);start=file.tell();skip(file,kind);end=file.tell()
                file.seek(start);value=file.read(end-start);metadata[key]=(kind,value)
            if metadata.get('general.architecture')!=(8,encoded('gemma3')):
                raise ValueError('Ожидался проверенный формат EmbeddingGemma gemma3')
            infos=[];shapes={}
            for _ in range(tensors):
                name=string(file);count=u32(file);dims=[u64(file) for _ in range(count)];dtype=u32(file);offset=u64(file)
                infos.append((name,dims,dtype,offset));shapes[name]=dims
            if not all(name in shapes for name in ['dense.0.weight','dense.1.weight']):raise ValueError('В GGUF отсутствуют проекционные слои EmbeddingGemma')
            alignment=struct.unpack('<I',metadata['general.alignment'][1])[0] if 'general.alignment' in metadata else 32
            data_offset=(file.tell()+alignment-1)//alignment*alignment
            translated={}
            for key,value in metadata.items():
                if key=='general.architecture':value=(8,encoded('gemma-embedding'))
                if key.startswith('gemma3.'):key='gemma-embedding.'+key[len('gemma3.'):]
                if key in ['gemma-embedding.attention.causal','gemma-embedding.attention.sliding_window_pattern']:continue
                translated[key]=value
            translated.setdefault('gemma-embedding.rope.freq_base_swa',(6,struct.pack('<f',10000.)))
            for name,prefix in [('dense.0.weight','dense_2'),('dense.1.weight','dense_3')]:
                translated['gemma-embedding.'+prefix+'_feat_in']=(4,struct.pack('<I',shapes[name][0]))
                translated['gemma-embedding.'+prefix+'_feat_out']=(4,struct.pack('<I',shapes[name][1]))
            renames={'dense.0.weight':'dense_2.weight','dense.1.weight':'dense_3.weight','norm.weight':'output_norm.weight'}
            with open(temporary,'wb') as result:
                result.write(struct.pack('<4sIQQ',magic,version,tensors,len(translated)))
                for key,(kind,value) in translated.items():result.write(encoded(key)+struct.pack('<I',kind)+value)
                for name,dims,dtype,offset in infos:
                    result.write(encoded(renames.get(name,name))+struct.pack('<I',len(dims))+struct.pack('<'+'Q'*len(dims),*dims)+struct.pack('<IQ',dtype,offset))
                remainder=(-result.tell())%alignment;result.write(b'\0'*remainder)
                file.seek(data_offset);shutil.copyfileobj(file,result,8*1024*1024)
        temporary.replace(target)
        return target
    finally:temporary.unlink(missing_ok=True)
