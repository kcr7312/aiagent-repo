# 이 폴더(schemas)가 import될 때 inquiry.py에 있는 InquiryAnalysis를 미리 노출시킴
from .inquiry import InquiryAnalysis

__all__ = ["InquiryAnalysis"] # 외부에서 'from schemas import *' 할 때 허용할 목록