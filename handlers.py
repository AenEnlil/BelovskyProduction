from aiogram import Router, Bot
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove
from aiogram import F

import text
from keyboard import main_menu, survey_confirm_menu, generate_survey_edit_menu, generate_event_type_menu,\
    survey_request_menu
from service import save_survey_to_db, generate_survey_confirm_text, check_if_user_can_start_survey, \
    notify_admin_about_new_client
from utils import format_message

router = Router()

chat_questions = {1: 'Как тебя зовут?', 2: 'Номер телефона для связи?'}
event_types = ['Cвадьба', 'День рождения', 'Корпоратив', 'Конференция', 'Другое']

user_data_map = {1: 'Имя', 2: 'Номер телефона'}

questions = {1: 'Как зовут молодоженов?', 2: 'Сколько лет?', 3: 'Как познакомились?',
             4: 'Какие увлечения/хобби?', 5: 'Любимый цвет?', 6: 'Любимые исполнители?',
             7: 'Предпочтительный стиль проведения мероприятия?', 8: 'Любимое время года?',
             9: 'Любимая марка авто?'}


class SurveyState(StatesGroup):
    chat_started = State()
    ready_to_survey = State()
    survey_started = State()
    survey_editing = State()


@router.message(Command('start'))
async def start_handler(msg: Message, state: FSMContext):
    current_state = await state.get_state()

    if not current_state:
        question_number = 1
        message = format_message(text.welcome_message, username=msg.from_user.username)
        await state.set_state(SurveyState.chat_started)
        await msg.answer(text=message, reply_markup=ReplyKeyboardRemove())
        question = chat_questions.get(question_number)
        send_question = await msg.answer(text=question)
        await state.update_data(last_question_number=question_number, user_data={},
                                message_to_delete=send_question.message_id)


@router.message(StateFilter(SurveyState.chat_started.state))
async def chat_question_answer_handler(msg: Message, state: FSMContext, bot: Bot):
    answer = msg.text
    state_data = await state.get_data()
    await msg.delete()
    if 'message_to_delete' in state_data:
        message_id = state_data.pop('message_to_delete')
        await bot.delete_message(chat_id=msg.chat.id, message_id=message_id)
    current_question_number, user_data = state_data.get('last_question_number'), state_data.get('user_data')
    user_data.update({user_data_map.get(current_question_number): answer})
    await state.update_data(user_data=user_data)

    if current_question_number != len(chat_questions):
        current_question_number += 1
        question = chat_questions.get(current_question_number)
        send_question = await msg.answer(text=question)
        await state.update_data(last_question_number=current_question_number,
                                message_to_delete=send_question.message_id)
    else:
        menu = generate_event_type_menu(event_types)
        await msg.answer(text=text.event_choose_message, reply_markup=menu.as_markup(), parse_mode='Markdown')


@router.callback_query(StateFilter(SurveyState.chat_started), F.data.startswith('event_'))
async def event_type_handler(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await bot.delete_message(chat_id=callback.message.chat.id, message_id=callback.message.message_id)

    event_type = callback.data.split('_')[-1]
    state_data = await state.get_data()
    user_data = state_data.get('user_data')
    user_data.update({'Мероприятие': event_type})
    await state.update_data(user_data=user_data)
    await notify_admin_about_new_client(user_data, bot)

    if event_type.lower() == 'другое':
        await bot.send_message(chat_id=callback.message.chat.id, text=text.other_event_reply)
    else:
        await bot.send_message(chat_id=callback.message.chat.id, text=text.event_survey_start_question,
                               reply_markup=survey_request_menu)


@router.callback_query(StateFilter(SurveyState.chat_started), F.data.startswith('surveyrequest'))
async def survey_request_handler(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.message.delete()
    want_to_start_survey = callback.data.split('_')[-1]
    if want_to_start_survey == 'yes':
        question_number = 1
        question = questions.get(question_number)

        await bot.send_message(chat_id=callback.message.chat.id, text=text.user_want_survey)
        await state.set_state(SurveyState.survey_started.state)
        send_question = await bot.send_message(chat_id=callback.message.chat.id, text=question)
        await state.update_data(last_question_number=question_number, survey_answers={},
                                message_to_delete=send_question.message_id)
    else:
        await bot.send_message(chat_id=callback.message.chat.id, text=text.user_dont_want_survey)


@router.message(F.text == f'{chr(0x1F4CB)} Опрос')
async def start_survey_handler(msg: Message, state: FSMContext):
    await msg.delete()
    if not await check_if_user_can_start_survey(msg.from_user.id):
        return await msg.answer(text=text.surveys_limit_reached)

    current_state = await state.get_state()

    if current_state in [SurveyState.ready_to_survey.state]:
        question_number = 1
        await state.set_state(SurveyState.survey_started)
        question = questions.get(question_number)
        send_question = await msg.answer(text=question)
        await state.update_data(last_question_number=question_number, survey_answers={}, message_to_delete=send_question.message_id)


@router.message(StateFilter(SurveyState.survey_started))
async def question_answer_handler(msg: Message, state: FSMContext, bot: Bot):
    answer = msg.text
    state_data = await state.get_data()
    await msg.delete()
    if 'message_to_delete' in state_data:
        message_id = state_data.pop('message_to_delete')
        await bot.delete_message(chat_id=msg.chat.id, message_id=message_id)
    current_question_number, survey_answers = state_data.get('last_question_number'), state_data.get('survey_answers')
    survey_answers.update({current_question_number: answer})

    if current_question_number != len(questions):
        current_question_number += 1
        question = questions.get(current_question_number)
        send_question = await msg.answer(text=question)
        await state.update_data(last_question_number=current_question_number, survey_answers=survey_answers,
                                message_to_delete=send_question.message_id)
    else:
        message = generate_survey_confirm_text(questions, survey_answers)

        await msg.answer(message, reply_markup=survey_confirm_menu, parse_mode='Markdown')


@router.callback_query(StateFilter(SurveyState.survey_started), F.data.startswith('surveymenu_confirm'))
async def survey_finish_handler(callback: CallbackQuery, state: FSMContext, bot: Bot):
    user_id = callback.from_user.id
    state_data = await state.get_data()
    await save_survey_to_db(user_id, state_data.get('survey_answers'), questions, state_data.get('user_data'))
    await state.set_state(SurveyState.ready_to_survey)
    await callback.answer()
    await callback.message.delete()
    await bot.send_message(chat_id=callback.message.chat.id, text=text.survey_finished_message, reply_markup=main_menu)


@router.callback_query(StateFilter(SurveyState.survey_started), F.data.startswith('surveymenu_edit'))
async def survey_edit_handler(callback: CallbackQuery, state: FSMContext, bot: Bot):
    message_id = callback.message.message_id
    await state.set_state(SurveyState.survey_editing)
    await state.update_data(edited_msg_id=message_id)
    message = 'Выберите какой вопрос вы хотите отредактировать: \n' + '\n'.join(f'{q_number}. {question}'
                                                                                for q_number, question in questions.items())
    await callback.answer()
    await bot.send_message(chat_id=callback.message.chat.id, text=message,
                           reply_markup=generate_survey_edit_menu(questions.keys()).as_markup())


@router.callback_query(StateFilter(SurveyState.survey_editing), F.data.startswith('answeredit_'))
async def edit_button_handler(callback: CallbackQuery, state: FSMContext, bot: Bot):
    question_number = callback.data.split('_')[-1]
    question = questions.get(int(question_number))
    await callback.answer()
    await callback.message.delete()
    send_question = await bot.send_message(chat_id=callback.message.chat.id, text=question)
    await state.update_data(edited_question_number=question_number, message_to_delete=send_question.message_id)


@router.message(StateFilter(SurveyState.survey_editing))
async def question_answer_handler(msg: Message, state: FSMContext, bot: Bot):
    answer = msg.text
    await msg.delete()
    state_data = await state.get_data()
    if 'message_to_delete' in state_data:
        message_id = state_data.pop('message_to_delete')
        await bot.delete_message(chat_id=msg.chat.id, message_id=message_id)
    edit_msg_id = state_data.get('edited_msg_id')
    edited_question_number, survey_answers = state_data.get('edited_question_number'), state_data.get('survey_answers')
    survey_answers.update({int(edited_question_number): answer})
    await state.set_state(SurveyState.survey_started)
    await state.update_data(survey_answers=survey_answers)
    message = generate_survey_confirm_text(questions, survey_answers)
    await bot.edit_message_text(chat_id=msg.chat.id, message_id=edit_msg_id, text=message,
                                reply_markup=survey_confirm_menu, parse_mode='Markdown')
