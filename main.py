import sys
import json
import os
from datetime import datetime
from PyQt6.QtCore import Qt, QPoint, QEvent
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QListWidget, QPushButton, QPlainTextEdit, QAbstractItemView
from PyQt6.QtGui import QTextCursor , QColor, QBrush 
import time




class TodoListWidget(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setStyleSheet("QListWidget { margin: 0px 10px; }")
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def dropEvent(self, event):
        super().dropEvent(event)
        # 드래그 앤 드롭 직후, 이동된 항목의 고유 순서값(order_id)을 재계산
        dropped_item = self.currentItem()
        if not dropped_item: return

        idx = self.row(dropped_item)

        # 위쪽 항목의 순서값 가져오기
        order_above = 0.0
        if idx > 0:
            item_above = self.item(idx - 1)
            order_above = float(item_above.data(Qt.ItemDataRole.UserRole) or 0.0)

        # 아래쪽 항목의 순서값 가져오기 (맨 밑으로 내렸을 경우 여유 있게 1000을 더함)
        order_below = order_above + 1000.0 
        if idx < self.count() - 1:
            item_below = self.item(idx + 1)
            order_below = float(item_below.data(Qt.ItemDataRole.UserRole) or order_above + 1000.0)

        # 새로운 순서값은 위와 아래의 정확히 중간값으로 세팅
        new_order = (order_above + order_below) / 2.0
        dropped_item.setData(Qt.ItemDataRole.UserRole, new_order)

        # 변경된 값을 기반으로 즉시 재정렬
        parent_widget = self.window()
        if hasattr(parent_widget, 'sort_todos'):
            parent_widget.sort_todos()




class ExpandingInput(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(32) # 기본 높이는 1줄 크기로 고정
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff) # 스크롤바 숨김
        
        self.document().setDocumentMargin(3)

        # [수정됨] 변경된 함수 이름으로 정확히 연결
        self.textChanged.connect(self.adjust_text_and_height)
        
        # [수정됨] 터미널 감성의 Monospace 폰트 설정 추가
        self.setStyleSheet("""
            QPlainTextEdit {
                background-color: #2d2d2d;
                border: 1px solid #555555;
                color: #ffffff;
                padding: 5px;
                font-family: Consolas, 'Courier New', monospace;
                font-size: 14px;
            }
        """)

    def adjust_text_and_height(self):
        text = self.toPlainText()
        parts = text.split("//", 1)
        
        # 1. 한글/영문 혼합 길이 방어 로직 (가중치 계산)
        max_weight = 22 # 한글 11글자(22점) 기준
        current_weight = 0
        truncated_task = ""
        
        # 할 일 부분(parts[0])의 텍스트를 한 글자씩 검사
        for char in parts[0]:
            # 알파벳, 숫자, 공백 등(ASCII)은 너비 1점, 한글 등 유니코드는 너비 2점
            char_weight = 1 if ord(char) <= 127 else 2
            
            # 다음 글자를 더했을 때 제한을 초과하면 즉시 중단
            if current_weight + char_weight > max_weight:
                break
                
            current_weight += char_weight
            truncated_task += char
            
        # 자른 텍스트가 원본과 다르다면 UI 강제 업데이트
        if parts[0] != truncated_task:
            parts[0] = truncated_task
            new_text = "//".join(parts) if len(parts) > 1 else parts[0]
            
            cursor = self.textCursor()
            pos = cursor.position()
            
            self.blockSignals(True) # 텍스트 변경 무한루프 에러 방지
            self.setPlainText(new_text)
            self.blockSignals(False)
            
            # 글자가 잘린 후 커서 위치가 맨 앞으로 튀는 현상 복구
            cursor.setPosition(min(pos, len(new_text)))
            self.setTextCursor(cursor)
            text = new_text

        # 2. 기존의 3배 확장 로직 유지
        if "//" in text:
            self.setFixedHeight(96)
        else:
            self.setFixedHeight(32)

    def keyPressEvent(self, event):
        # 1. 엔터 키 입력 시 등록 처리 (기존 로직)
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            parent_widget = self.window()
            if hasattr(parent_widget, 'add_todo'):
                parent_widget.add_todo()
            return

        # 2. '//' 입력 시 자동 줄바꿈 처리
        if event.text() == '/':
            cursor = self.textCursor()
            # 현재 커서 위치에서 바로 앞의 1글자를 드래그하듯 선택
            cursor.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.KeepAnchor, 1)
            
            # 그 1글자가 '/'라면 (즉, 방금 '/'를 눌러서 '//'가 완성되는 순간이라면)
            if cursor.selectedText() == '/':
                super().keyPressEvent(event) # 1. 사용자가 누른 두 번째 '/'를 화면에 먼저 띄움
                self.insertPlainText("\n")   # 2. 그 직후 줄바꿈('\n') 기호를 강제 삽입
                return

        # 3. 나머지 모든 키보드 입력은 기본 동작 수행
        super().keyPressEvent(event)


class TododoApp(QWidget):
    def __init__(self):
        super().__init__()
        self.is_always_on_top = False # [신규] 기본 상태는 '항상 위 아님(초록색)'
        self.initUI()
        self.oldPos = self.pos()
        self.load_todos()

    def initUI(self):
        
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.resize(300, 400)
        
        # 2. 스타일시트 세팅 (기존과 동일)
        self.setStyleSheet("""
            QWidget {
                background-color: #1e1e1e;
                color: #ffffff;
                font-family: Consolas, 'Courier New', monospace;
                font-size: 14px;
            }
            QListWidget {
                background-color: #1e1e1e;
                border: none;
            }
            QListWidget::item {
                padding: 5px;
            }
            QListWidget::item:selected {
                background-color: #3d3d3d;
            }
            QPushButton {
                background-color: #2d2d2d;
                border: 1px solid #555555;
                font-size: 11px;
                color: #ffffff;
            }
            QPushButton:hover {
                background-color: #3d3d3d;
            }
        """)

        # 3. 레이아웃 구성
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 10) # 타이틀 바를 창 최상단에 밀착시키기 위해 상단 여백 0으로 변경

        # --- [신규] 상단 타이틀 바 및 중앙 스위치 ---
        self.title_bar = QWidget()
        self.title_bar.setFixedHeight(25)
        self.title_bar.setStyleSheet("background-color: #2a2a2a; border-bottom: 1px solid #111111;")
        
        title_layout = QHBoxLayout(self.title_bar)
        title_layout.setContentsMargins(0, 0, 0, 0)
        
        # 스위치 버튼 생성
        self.btn_ontop = QPushButton()
        self.btn_ontop.setFixedSize(12, 12)
        # 기본 상태 초록색 세팅 (border-radius로 완벽한 원형 구현)
        self.btn_ontop.setStyleSheet("background-color: #4CAF50; border-radius: 6px; border: none;")
        self.btn_ontop.clicked.connect(self.toggle_always_on_top)
        
        # 버튼을 중앙에 배치 (양옆에 신축성 있는 빈 공간 추가)
        title_layout.addStretch()
        title_layout.addWidget(self.btn_ontop)
        title_layout.addStretch()
        
        layout.addWidget(self.title_bar)

        # --- 리스트 위젯 (커스텀 위젯으로 교체) ---
        self.list_widget = TodoListWidget(self)
        self.list_widget.itemClicked.connect(self.handle_item_click)
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self.instant_delete_item)
        layout.addWidget(self.list_widget)

        # --- 하단 영역 ---
        bottom_layout = QHBoxLayout()
        bottom_layout.setContentsMargins(10, 0, 10, 0)

        self.input_field = ExpandingInput(self)
        self.input_field.setPlaceholderText("TODO // Remark")
        bottom_layout.addWidget(self.input_field)

        self.btn_important = QPushButton("강조")
        self.btn_important.setFixedSize(40, 40)
        self.btn_important.clicked.connect(self.toggle_important)
        bottom_layout.addWidget(self.btn_important)

        self.btn_clear = QPushButton("전체\n삭제")
        self.btn_clear.setFixedSize(40, 40)
        self.btn_clear.clicked.connect(self.clear_all_todos)
        bottom_layout.addWidget(self.btn_clear)

        layout.addLayout(bottom_layout)
        self.setLayout(layout)


   # --- 상태 전환 로직 ---
    def toggle_always_on_top(self):
        self.is_always_on_top = not self.is_always_on_top
        
        if self.is_always_on_top:
            # 붉은색 (항상 위 켜짐, 작업 표시줄 유지)
            self.btn_ontop.setStyleSheet("background-color: #F44336; border-radius: 6px; border: none;")
            self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        else:
            # 초록색 (일반 창 속성, 항상 위 꺼짐, 작업 표시줄 유지)
            self.btn_ontop.setStyleSheet("background-color: #4CAF50; border-radius: 6px; border: none;")
            self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        
        # 속성 변경 후 창이 숨겨지는 현상을 방지하기 위해 다시 화면에 호출
        self.show()

    # --- 기존 데이터 관리 로직들  ---
    def add_todo(self):
        raw_text = self.input_field.toPlainText().strip()
        if raw_text:
            parts = raw_text.split("//", 1)
            task_text = parts[0].strip()
            note_text = parts[1].strip() if len(parts) > 1 else ""

            # [신규 추가] 강조 버튼이 켜져 있었다면 텍스트에 태그를 병합하고 버튼 상태 초기화
            if getattr(self, 'is_next_important', False):
                task_text = f"[강조] {task_text}"
                self.is_next_important = False
                self.btn_important.setStyleSheet("") # 버튼 시각 효과 원래대로 끄기

            now_str = datetime.now().strftime("%y/%m/%d %H:%M")
            self.list_widget.addItem(f"> {task_text}")
            
            last_item = self.list_widget.item(self.list_widget.count() - 1)
            last_item.setData(Qt.ItemDataRole.UserRole, time.time())
            
            tooltip_text = f"생성: {now_str}"
            if note_text:
                tooltip_text += f"\n특이사항: {note_text}"
            last_item.setToolTip(tooltip_text)
            
            self.input_field.clear()
            self.sort_todos()


    
    
    def save_todos(self):
        todos = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            todo_data = {
                "text": item.text(),
                "is_checked": item.font().strikeOut(),
                "tooltip": item.toolTip(),
                "order_id": float(item.data(Qt.ItemDataRole.UserRole) or 0.0) # 순서값 저장
            }
            todos.append(todo_data)
        
        with open("todo_data.json", "w", encoding="utf-8") as f:
            json.dump(todos, f, ensure_ascii=False, indent=4)

    def load_todos(self):
        if os.path.exists("todo_data.json"):
            try:
                with open("todo_data.json", "r", encoding="utf-8") as f:
                    todos = json.load(f)
                    for idx, todo_data in enumerate(todos):
                        self.list_widget.addItem(todo_data["text"])
                        last_item = self.list_widget.item(self.list_widget.count() - 1)
                        
                        if "tooltip" in todo_data:
                            last_item.setToolTip(todo_data["tooltip"])
                        
                        # 데이터 복구 (과거 데이터 호환을 위해 없으면 임의 시간 부여)
                        order_id = todo_data.get("order_id", time.time() + idx)
                        last_item.setData(Qt.ItemDataRole.UserRole, order_id)

                        # 색상 복구
                        if todo_data.get("is_checked", False):
                            font = last_item.font()
                            font.setStrikeOut(True)
                            last_item.setFont(font)
                            last_item.setForeground(QBrush(QColor("#666666")))
                        elif "[강조]" in todo_data["text"]:
                            last_item.setForeground(QBrush(QColor("#FFD700")))
            except Exception as e:
                print(f"데이터를 불러오는 중 오류 발생: {e}")




    def instant_delete_item(self, position):
        item = self.list_widget.itemAt(position)
        if item:
            self.list_widget.takeItem(self.list_widget.row(item))
            self.save_todos()

    def clear_all_todos(self):
        self.list_widget.clear()
        self.save_todos()

    def toggle_important(self):
        # 1. 리스트에 명시적으로 선택된 항목이 있는지 확인
        selected_items = self.list_widget.selectedItems()
        
        if selected_items:
            # 기존 기능: 선택된 항목의 강조 상태 토글
            current_item = selected_items[0]
            text = current_item.text()
            if "[강조]" in text:
                current_item.setText(text.replace("[강조] ", ""))
            else:
                current_item.setText(text.replace("> ", "> [강조] "))
            self.sort_todos()
            self.list_widget.clearSelection() # 작업 완료 후 선택을 해제하여 상태 꼬임 방지
            
        else:
            # 본래 기획: 신규 입력 대기 모드 토글
            self.is_next_important = not getattr(self, 'is_next_important', False)
            
            if self.is_next_important:
                # 활성화 시 시각적 피드백 (노란색 배경, 검은색 굵은 글씨)
                self.btn_important.setStyleSheet("background-color: #FFD700; color: #1e1e1e; font-weight: bold; border: none;")
            else:
                # 비활성화 시 QSS 부모 스타일로 복구
                self.btn_important.setStyleSheet("") 
            
            # 버튼 클릭 후 곧바로 다시 타자를 칠 수 있게 입력창으로 포커스 강제 이동
            self.input_field.setFocus()

    

    
    def sort_todos(self):
        items_data = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            text = item.text()
            is_checked = item.font().strikeOut()
            tooltip = item.toolTip()
            is_important = "[강조]" in text
            order_id = float(item.data(Qt.ItemDataRole.UserRole) or 0.0)

            # [핵심] 정렬 3순위로 고유 순서값(order_id)을 넣어 원래 자리를 완벽하게 기억함
            sort_key = (is_checked, not is_important, order_id)

            items_data.append({
                "text": text, "is_checked": is_checked, "is_important": is_important,
                "tooltip": tooltip, "order_id": order_id, "sort_key": sort_key
            })

        items_data.sort(key=lambda x: x["sort_key"])

        self.list_widget.clear()
        for data in items_data:
            self.list_widget.addItem(data["text"])
            new_item = self.list_widget.item(self.list_widget.count() - 1)
            
            if data["tooltip"]:
                new_item.setToolTip(data["tooltip"])
                
            new_item.setData(Qt.ItemDataRole.UserRole, data["order_id"])
            
            # [신규] 시각적 피드백 (색상 및 취소선) 적용
            if data["is_checked"]:
                font = new_item.font()
                font.setStrikeOut(True)
                new_item.setFont(font)
                new_item.setForeground(QBrush(QColor("#666666"))) # 완료된 일은 흐릿한 회색
            elif data["is_important"]:
                new_item.setForeground(QBrush(QColor("#FFD700"))) # 강조된 일은 눈에 띄는 노란색
            else:
                new_item.setForeground(QBrush(QColor("#ffffff"))) # 기본 흰색

        self.save_todos()



    def handle_item_click(self, item):
        # 현재 눌려있는 키보드 상태(Modifier)를 확인
        modifiers = QApplication.keyboardModifiers()
        
        # 1. Shift 키가 눌린 상태라면 아무 동작도 하지 않고 함수를 즉시 종료
        # -> 리스트 위젯의 기본 성질인 '선택(회색 배경)' 처리만 깔끔하게 남게 됨
        if modifiers == Qt.KeyboardModifier.ShiftModifier:
            return

        # 2. 일반 좌클릭인 경우: 본래 기획대로 취소선(완료) 처리 수행
        font = item.font()
        font.setStrikeOut(not font.strikeOut())
        item.setFont(font)
        
        # 일반 클릭 시 선택 상태가 화면에 잠깐 남아서 UX가 꼬이는 현상을 방지
        self.list_widget.clearSelection()
        # 상태가 변경되었으므로 즉시 자동 정렬 및 저장
        self.sort_todos()
            
        

    # ---  창 이동 로직 (오직 타이틀 바에서만 드래그 허용) ---
    def mousePressEvent(self, event):
        # 마우스 클릭이 발생한 위치가 타이틀 바 영역 안인지 확인
        if event.button() == Qt.MouseButton.LeftButton and self.title_bar.geometry().contains(event.pos()):
            self.oldPos = event.globalPosition().toPoint()
            self.is_dragging = True
        else:
            self.is_dragging = False

    def mouseMoveEvent(self, event):
        if getattr(self, 'is_dragging', False) and not self.oldPos.isNull():
            delta = event.globalPosition().toPoint() - self.oldPos
            self.move(self.pos() + delta)
            self.oldPos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.oldPos = QPoint()
            self.is_dragging = False

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()



if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = TododoApp()
    ex.show()
    sys.exit(app.exec())