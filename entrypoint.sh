source /run/secrets/alpha-service/key
if [[ $PRODUCTION_MODE == "1" ]]
then
	python app/alerts.py
else
	python -u app/alerts.py
fi