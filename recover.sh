cd ~/rock-server
git pull origin master
sudo systemctl restart rock-server
sudo systemctl restart reminders-runner
sleep 5s
systemctl status rock-server
systemctl status reminders-runner
