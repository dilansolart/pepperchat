#!/usr/bin/env python
# -*- coding: utf-8 -*-

###########################################################
# This module implements the main dialogue functionality for Pepper, based on ChatGPT.
#
# Syntax:
#    python scriptname --pip <ip> --pport <port>
#
#    --pip <ip>: specify the ip of your robot (without specification it will use the ROBOT_IP defined below
#
# Author: Erik Billing, University of Skovde based on code from Johannes Bramauer, Vienna University of Technology
# Created: May 30, 2018 and updated spring progressively during in the period 2022-05 to 2024-04. 
# License: MIT
###########################################################

ROBOT_PORT = 9559 # Robot
ROBOT_IP = "pepper.local" # Pepper default

from optparse import OptionParser
import re
from unicodedata import normalize
import naoqi
import time
import sys, os
import codecs
from naoqi import ALProxy
from oaichat.oaiclient import OaiClient

START_PROMPT = codecs.open(os.getenv('OPENAI_PROMPTFILE'),encoding='utf-8').read() if os.path.isfile(os.getenv('OPENAI_PROMPTFILE')) else None
participantId = raw_input('Participant ID: ')
ALIVE = int(participantId) % 2 == 1

chatbot = OaiClient(user=participantId)
chatbot.reset()


class DialogueModule(naoqi.ALModule):
    """
    Main dialogue module. Depends on both the ChatGPT service and the Speech Recognion module.
    """
    
    def __init__( self, strModuleName, strNaoIp ):
        self.misunderstandings=0
        self.log = codecs.open('dialogue.log','a',encoding='utf-8')
        try:
            naoqi.ALModule.__init__(self, strModuleName )
            self.BIND_PYTHON( self.getName(),"callback" )
            self.strNaoIp = strNaoIp
            #self.session = qi.Session()
        except BaseException, err:
            print( "ERR: ReceiverModule: loading error: %s" % str(err) )
 
    def __del__( self ):
        print( "INF: ReceiverModule.__del__: cleaning everything" )
        self.stop()

    def start( self ):
        self.configureSpeechRecognition()
        self.memory = naoqi.ALProxy("ALMemory", self.strNaoIp, ROBOT_PORT)
        self.memory.subscribeToEvent("SpeechRecognition", self.getName(), "processRemote")
        print( "INF: ReceiverModule: started!" )
        try:
            self.posture = ALProxy("ALRobotPosture", self.strNaoIp, ROBOT_PORT)
            if ALIVE:
                self.aup = ALProxy("ALAnimatedSpeech",  self.strNaoIp, ROBOT_PORT)
            else:
                self.aup = ALProxy("ALTextToSpeech",  self.strNaoIp, ROBOT_PORT)
        except RuntimeError:
            print ("Soy GPT, no me puedo conectar con Lied en la IP \"" + self.strNaoIp + "\" en el puerto " + str(ROBOT_PORT) +".\n"
               "Por favor, comprueba los argumentos de tu script. Ejecútelo con la opción -h para obtener ayuda.")

        if START_PROMPT:
            answer = chatbot.respond(START_PROMPT)
            answer = self.encode(chatbot.respond(START_PROMPT))
            self.aup.say(answer)
        self.listen(True)
        print('Listening...')

    def stop( self ):
        print( "INF: ReceiverModule: stopping..." )
        self.memory.unsubscribe(self.getName())
        print( "INF: ReceiverModule: stopped!" )

    def version( self ):
        return "2.0"

    def configureSpeechRecognition(self):
        self.speechRecognition = ALProxy("SpeechRecognition")
        #self.speechRecognition.calibrate()

        AUTODEC = True
        if(AUTODEC==False):
            print("False, auto-detection not available")
            #one-shot recording for at least 5 seconds
            self.speechRecognition = ALProxy("SpeechRecognition")
            self.speechRecognition.start()
            self.speechRecognition.setHoldTime(5)
            self.speechRecognition.setIdleReleaseTime(1.7)
            self.speechRecognition.setMaxRecordingDuration(10)
            #self.speechRecognition.startRecording()
        else:
            print("True, auto-detection selected")
            # auto-detection
            self.speechRecognition = ALProxy("SpeechRecognition")
            #self.speechRecognition.start()
            self.speechRecognition.setHoldTime(2.5)
            self.speechRecognition.setIdleReleaseTime(2.0)
            self.speechRecognition.setMaxRecordingDuration(10)
            self.speechRecognition.setLookaheadDuration(0.5)
            #self.speechRecognition.setLanguage("de-de")
            #self.speechRecognition.calibrate()
            self.speechRecognition.setAutoDetectionThreshold(8)
            #self.speechRecognition.startRecording()
        self.listen(False) # Ensure that speech recog is off from previous instance. 

    def listen(self,enable):
        if enable:
            self.speechRecognition.start()
            self.speechRecognition.enableAutoDetection()
        else:
            #always disable to not detect its own speech
            self.speechRecognition.disableAutoDetection()
            #and stop if it was already recording another time
            self.speechRecognition.pause()

    def encode(self,s):
        '''Takes a byte string as param and convert it into a unicode one.
        First tries UTF8, and fallback to Latin1 if it fails'''
        cr = None
        try:
            cr = s.decode('utf8')
        except UnicodeDecodeError:
            cr = s.decode('latin1')
        return cr



    def processRemote(self, signalName, message):
        self.log.write('INP: ' + message + '\n')
        if message == 'error': 
            #print('Input not recognized, continue listen')
            return
        self.listen(False)
        
        # received speech recognition result
        print("USER: \n"+message)
        #computing answer
        if message=='error':
            self.misunderstandings +=1
            if self.misunderstandings ==1:
                answer="No lo he entendido, ¿puede repetirlo?"
            elif self.misunderstandings == 2:
                answer="Perdona que no lo haya entendido, ¿puedes decirlo una vez más?"
            elif self.misunderstandings == 3:
                answer="Hoy tengo problemas para entender lo que dices, lo siento."
            else:
                answer="Por favor, repite eso."
            print('ERROR, DEFAULT ANSWER:\n'+answer)
        else:
            self.misunderstandings = 0
            answer = self.encode(chatbot.respond(message))
            print('ROBOT:\n'+answer)
        #text to speech the answer
        self.log.write('ANS: ' + answer + '\n')
        self.aup.say(answer)
        self.react(answer)
        #time.sleep(2)
        self.listen(True)

    def react(self,s):
        if re.match(".*I.*sit down.*",s): # Sitting down
            self.posture.goToPosture("Sit",1.0)
        elif re.match(".*Yo.*Levantate.*",s): # Standing up
            self.posture.goToPosture("Stand",1.0)
        elif re.match(".*I.*(lie|lyi).*down.*",s): # Lying down
            self.posture.goToPosture("LyingBack",1.0)
        

def main():
    """ Main entry point

    """

    parser = OptionParser()
    parser.add_option("--pip",
        help="Parent broker port. The IP address or your robot",
        dest="pip")
    parser.add_option("--pport",
        help="Parent broker port. The port NAOqi is listening to",
        dest="pport",
        type="int")
    parser.set_defaults(
        pip=ROBOT_IP,
        pport=ROBOT_PORT)

    (opts, args_) = parser.parse_args()
    pip   = opts.pip
    pport = opts.pport

    # We need this broker to be able to construct
    # NAOqi modules and subscribe to other modules
    # The broker must stay alive until the program exists
    myBroker = naoqi.ALBroker("myBroker",
       "0.0.0.0",   # listen to anyone
       0,           # find a free port and use it
       pip,         # parent broker IP
       pport)       # parent broker port



    try:
        p = ALProxy("dialogueModule")
        p.exit()  # kill previous instance
    except:
        pass

    audio = ALProxy("ALAudioDevice")
    audio.setOutputVolume(70)

    AutonomousLife = ALProxy('ALAutonomousLife')
    RobotPosture = ALProxy('ALRobotPosture')
    if ALIVE:
        AutonomousLife.setState('solitary')
        AutonomousLife.stopAll()
        AutonomousLife.switchFocus('lieddialog-ca66b6/behavior_1')
        #AutonomousLife.switchFocus('julia-8b4016/behavior_1') Modificado Dilan lieddialog-ca66b6/behavior_1
        print('Numero de participante impar, vida autonoma activada (autonomous life enabled)')
    else:
        if AutonomousLife.getState() != 'disabled':
            AutonomousLife.setState('disabled')
        RobotPosture.goToPosture('Stand',0.5)
        print('Numero de participante par, vida autonoma desactivada (autonomous life disabled)')

    TabletService = ALProxy('ALTabletService')
    TabletService.goToSleep()
    
    # Reinstantiate module

    # Warning: ReceiverModule must be a global variable
    # The name given to the constructor must be the name of the
    # variable
    global dialogueModule
    dialogueModule = DialogueModule("dialogueModule", pip)
    dialogueModule.start()

    try:
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print
        print("Interrupted by user, shutting down")
        myBroker.shutdown()
        sys.exit(0)



if __name__ == "__main__":
    main()