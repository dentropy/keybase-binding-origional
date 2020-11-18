from string import Template
import subprocess
import json
from database import DB, Messages, Users
from urlextract import URLExtract
import datetime

class ExportKeybase():
    def __init__(self):
        """Initialize the ExportKeybase object."""
        self.extractor = URLExtract()
    
    def get_teams(self):
        """Return string list of all current-user Keybase teams."""
        keybase_teams = subprocess.check_output(["keybase", "team", "list-memberships"])
        team_string = str(keybase_teams).split("\\n")
        teams = []
        for i in team_string[1:-1]:
            teams.append(i.split()[0])
        return teams

    def get_team_memberships(self, team_name):
        """Return string list of all users for a specific team."""
        json_string = '''
        {
            "method": "list-team-memberships",
            "params": {
                "options": {
                    "team": "%s"
                }
            }
        }
        ''' % (team_name)
        response = subprocess.check_output(["keybase", "team", "api", "-m", json_string])
        user_data = json.loads(response.decode('utf-8'))
        usernames = []
        for key in user_data["result"]["members"].keys():
            if user_data["result"]["members"][key] != None:
                for mah_val in range(len(user_data["result"]["members"][key])):
                    usernames.append(user_data["result"]["members"][key][mah_val]["username"])
        return usernames
    
    def get_user_metadata(self, username):
        """Get string of URLs for accounts that user has linked with Keybase account."""
        user_metadata = {"verification":[]}
        response = subprocess.check_output(["keybase", "id", username],stderr=subprocess.STDOUT, encoding="utf-8")
        response_string = str(response)[1:-1]#response.decode("utf-8")
        for line in response_string.split("\n"):
            if "admin of" in line:
                user_metadata["verification"].append(line.split()[6][5:-6])
        for url in self.extractor.find_urls(response_string):
            user_metadata["verification"].append(url)
        json_string = '''
        {
            "method": "list-user-memberships", 
            "params": {
                "options": {"username": "%s"}
            }
        }
        ''' % (username)
        response = json.loads(subprocess.check_output(["keybase", "team", "api", "-m", json_string]).decode('utf-8'))
        team_list = []
        for team in response["result"]["teams"]:
            team_list.append(team["fq_name"])
        user_metadata["teams"] = team_list
        user_metadata["followers"] = subprocess.check_output(["keybase", "list-followers", username],stderr=subprocess.STDOUT, encoding="utf-8").split("\n")
        user_metadata["following"] = subprocess.check_output(["keybase", "list-following", username],stderr=subprocess.STDOUT, encoding="utf-8").split("\n")
        return user_metadata

    def export_team_user_metadata_sql(self, team_name, sql_connection_string):
        """Write a json file of all users and metadata for a given team."""
        db = DB(sql_connection_string)
        member_list = self.get_team_memberships(team_name)
        members = {}
        for member in member_list:
            print("Getting " + member + "'s metadata")
            user_metadata = self.get_user_metadata(member)
            db.session.add( Users( 
                username = member, 
                teams = json.dumps(user_metadata["teams"]), 
                verification = json.dumps(user_metadata["verification"]), 
                followers = json.dumps(user_metadata["followers"]), 
                following =  json.dumps(user_metadata["following"]),
            ))
            members[member] = self.get_user_metadata(member)
        #    members[member]["teams"] = self.get_team_memberships(member)
        db.session.commit()
        return members

    def export_team_user_metadata_sqlite(self, team_name, sqlite):
        """Write a json file of all users and metadata for a given team."""
        member_list = self.get_team_memberships(team_name)
        members = {}
        for member in member_list:
            members[member] = self.get_user_metadata(member)
        #    members[member]["teams"] = self.get_team_memberships(member)
        with open(json_file, 'w') as fp:
            json.dump(members, fp)
        return members

    def get_team_channels(self,keybase_team_name):
        """Returns list of strings for each text channel on a team."""
        get_teams_channels = Template('''
        {
            "method": "listconvsonname",
            "params": {
                "options": {
                    "topic_type": "CHAT",
                    "members_type": "team",
                    "name": "$TEAM_NAME"
                }
            }
        }
        ''')
        dentropydaemon_channels_json = get_teams_channels.substitute(TEAM_NAME=keybase_team_name)
        dentropydaemon_channels = subprocess.check_output(["keybase", "chat", "api", "-m", dentropydaemon_channels_json])
        dentropydaemon_channels = str(dentropydaemon_channels)[2:-3]
        mah_json = json.loads(dentropydaemon_channels)
        mah_channels = []
        for i in mah_json["result"]["conversations"]:
            mah_channels.append(i["channel"]["topic_name"])
        return mah_channels

    def get_team_chat_channel(self, keybase_team_name, keybase_topic_name):
        """Returns json object of all messages within a Keybase team topic"""
        get_teams_channels = Template('''
        {
            "method": "read",
            "params": {
                "options": {
                    "channel": {
                        "name": "$TEAM_NAME",
                        "members_type": "team",
                        "topic_name": "$TOPIC_NAME"
                    }
                }
            }
        }
        ''')
        dentropydaemon_channels_json = get_teams_channels.substitute(TEAM_NAME=keybase_team_name, TOPIC_NAME=keybase_topic_name)
        command = ["keybase", "chat", "api", "-m", dentropydaemon_channels_json]
        response = subprocess.check_output(command)
        return json.loads(response.decode('utf-8'))

    def generate_json_export(self, keybase_team, output_file):
        """Creates a json file with specified filename containing all team chat data."""
        complexity_weekend_teams = self.get_team_channels(keybase_team)
        mah_messages = {"topic_name":{}}
        for topic in complexity_weekend_teams:
            result_msgs = self.get_team_chat_channel(keybase_team, topic)
            result_msgs["result"]["messages"].reverse()
            mah_messages["topic_name"][topic] = result_msgs

        text_file = open(output_file, "w")
        text_file.write(json.dumps(mah_messages))
        text_file.close()


    def get_root_messages(self, mah_messages, db):
        """From message list, find text messages, add them to SQL database session, and then commit the session."""
        for topic in mah_messages["topic_name"]:
            for message in mah_messages["topic_name"][topic]["result"]["messages"]:
                if message["msg"]["content"]["type"] == "headline":
                    db.session.add( Messages( 
                        team = "complexityweekend.oct2020", 
                        topic = topic,
                        msg_id = message["msg"]["id"],
                        msg_type = "headline",
                        txt_body =  message["msg"]["content"]["headline"]["headline"],
                        from_user = message["msg"]["sender"]["username"],
                        sent_time = datetime.datetime.utcfromtimestamp(message["msg"]["sent_at"]),
                        ))
                elif message["msg"]["content"]["type"] == "join":
                    db.session.add( Messages( 
                        team = "complexityweekend.oct2020", 
                        topic = topic,
                        msg_id = message["msg"]["id"],
                        msg_type = "join",
                        from_user = message["msg"]["sender"]["username"],
                        sent_time = datetime.datetime.utcfromtimestamp(message["msg"]["sent_at"]),
                        ))
                elif message["msg"]["content"]["type"] == "metadata":
                    db.session.add( Messages( 
                        team = "complexityweekend.oct2020", 
                        topic = topic,
                        msg_id = message["msg"]["id"],
                        msg_type = "metadata",
                        from_user = message["msg"]["sender"]["username"],
                        txt_body =  json.dumps(message["msg"]["content"]["metadata"]),
                        sent_time = datetime.datetime.utcfromtimestamp(message["msg"]["sent_at"])
                        ))
                elif message["msg"]["content"]["type"] == "attachment":
                    db.session.add( Messages( 
                        team = "complexityweekend.oct2020", 
                        topic = topic,
                        msg_id = message["msg"]["id"],
                        msg_type = "attachment",
                        from_user = message["msg"]["sender"]["username"],
                        txt_body =  json.dumps(message["msg"]["content"]["attachment"]),
                        sent_time = datetime.datetime.utcfromtimestamp(message["msg"]["sent_at"])
                        ))
                elif message["msg"]["content"]["type"] == "unfurl":
                    db.session.add( Messages( 
                        team = "complexityweekend.oct2020", 
                        topic = topic,
                        msg_id = message["msg"]["id"],
                        msg_type = "unfurl",
                        from_user = message["msg"]["sender"]["username"],
                        txt_body =  json.dumps(message["msg"]["content"]["unfurl"]),
                        sent_time = datetime.datetime.utcfromtimestamp(message["msg"]["sent_at"])
                        ))
                elif message["msg"]["content"]["type"] == "system":
                    if "at_mention_usernames" in message["msg"]:
                        at_mention_usernames = json.dumps(message["msg"]["at_mention_usernames"])
                    else:
                        at_mention_usernames = None
                    db.session.add( Messages( 
                        team = "complexityweekend.oct2020", 
                        topic = topic,
                        msg_id = message["msg"]["id"],
                        msg_type = "system",
                        from_user = message["msg"]["sender"]["username"],
                        txt_body =  json.dumps(message["msg"]["content"]["system"]),
                        sent_time = datetime.datetime.utcfromtimestamp(message["msg"]["sent_at"]),
                        userMentions = at_mention_usernames
                        ))
                elif message["msg"]["content"]["type"] == "leave":
                    db.session.add( Messages( 
                        team = "complexityweekend.oct2020", 
                        topic = topic,
                        msg_id = message["msg"]["id"],
                        msg_type = "leave",
                        from_user = message["msg"]["sender"]["username"],
                        sent_time = datetime.datetime.utcfromtimestamp(message["msg"]["sent_at"]),
                        ))
                elif message["msg"]["content"]["type"] == "delete":
                    db.session.add( Messages( 
                        team = "complexityweekend.oct2020", 
                        topic = topic,
                        msg_id = message["msg"]["id"],
                        msg_type = "delete",
                        from_user = message["msg"]["sender"]["username"],
                        sent_time = datetime.datetime.utcfromtimestamp(message["msg"]["sent_at"]),
                        msg_reference = message["msg"]["content"]["delete"]["messageIDs"][0]
                        ))
                elif message["msg"]["content"]["type"] == "text":
                    urls = self.extractor.find_urls(message["msg"]["content"]["text"]["body"])
                    if len(urls) == 0:
                        db.session.add( Messages( 
                            team = "complexityweekend.oct2020", 
                            topic = topic,
                            msg_id = message["msg"]["id"],
                            msg_type = "text",
                            from_user = message["msg"]["sender"]["username"],
                            sent_time = datetime.datetime.utcfromtimestamp(message["msg"]["sent_at"]),
                            txt_body =  message["msg"]["content"]["text"]["body"],
                            word_count = len(message["msg"]["content"]["text"]["body"].split(" ")),
                            userMentions = json.dumps(message["msg"]["content"]["text"]["userMentions"])
                            ))
                    else:
                        db.session.add( Messages( 
                            team = "complexityweekend.oct2020", 
                            topic = topic,
                            msg_id = message["msg"]["id"],
                            msg_type = "text",
                            from_user = message["msg"]["sender"]["username"],
                            sent_time = datetime.datetime.utcfromtimestamp(message["msg"]["sent_at"]),
                            txt_body =  message["msg"]["content"]["text"]["body"],
                            urls = json.dumps(urls),
                            num_urls = len(urls),
                            word_count = len(message["msg"]["content"]["text"]["body"].split(" ")),
                            userMentions = json.dumps(message["msg"]["content"]["text"]["userMentions"])
                            ))
        db.session.commit()
    
    def get_reaction_messages(self, mah_messages, db):
        """From message list, find reactions, add them to SQL database session, and then commit the session."""
        for topic in mah_messages["topic_name"]:
            for message in mah_messages["topic_name"][topic]["result"]["messages"]:
                if message["msg"]["content"]["type"] == "reaction":
                    root_msg_id = message["msg"]["content"]["reaction"]["m"]
                    root_msg = db.session.query(Messages).filter_by(topic=topic).filter_by(msg_id = root_msg_id)
                    if root_msg.count() == 1:
                        db.session.add( Messages( 
                            team = "complexityweekend.oct2020", 
                            topic = topic,
                            msg_id = message["msg"]["id"],
                            msg_type = "reaction",
                            from_user = message["msg"]["sender"]["username"],
                            sent_time = datetime.datetime.utcfromtimestamp(message["msg"]["sent_at"]),
                            reaction_body =  message["msg"]["content"]["reaction"]["b"],
                            msg_reference = root_msg.first().id
                        ))
                if message["msg"]["content"]["type"] == "edit":
                    root_msg_id = message["msg"]["content"]["edit"]["messageID"]
                    root_msg = db.session.query(Messages).filter_by(topic=topic).filter_by(msg_id = root_msg_id)
                    if root_msg.count() == 1:
                        db.session.add( Messages( 
                            team = "complexityweekend.oct2020", 
                            topic = topic,
                            msg_id = message["msg"]["id"],
                            msg_type = "edit",
                            txt_body =  message["msg"]["content"]["edit"]["body"],
                            from_user = message["msg"]["sender"]["username"],
                            sent_time = datetime.datetime.utcfromtimestamp(message["msg"]["sent_at"]),
                            msg_reference = root_msg.first().id
                        ))
        db.session.commit()
        
    def convert_json_to_sql(self, json_file, sql_connection_string):
        """Convert json file data to SQL database structure."""
        db = DB(sql_connection_string)
        mah_messages = json.load(open(json_file, 'r'))
        self.get_root_messages(mah_messages,db)
        self.get_reaction_messages(mah_messages, db)
        print("Conversion from json to sql complete")

    def export_text_msgs_to_csv(self, sql_connection_string, output_file):
        """Export text messages from SQL database to CSV spreadsheet."""
        db = DB(sql_connection_string)
        mah_messages = db.session.query(Messages).filter_by(msg_type = "text")
        msg_list = [["text_messages"]]
        for message in mah_messages:
            msg_list.append([str(message.txt_body)])
        import csv
        with open(output_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerows(msg_list)

    def message_table_to_csv(self, table_object, sql_connection_string, csv_file_name):
        """Export table object with text message data to CSV spreadsheet."""
        db = DB(sql_connection_string)
        mah_columns = []
        for column in table_object.__table__.c:
            mah_columns.append(str(column).split(".")[1])
        import csv
        with open(csv_file_name, 'w') as f:
            out = csv.writer(f)
            for row in db.session.query(table_object).all():
                full_row = []
                for column_name in mah_columns:
                    full_row.append(row.__dict__[column_name])
                out.writerow(full_row)
