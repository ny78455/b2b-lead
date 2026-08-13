from backend.services.calendar import generate_meeting_link

def test_cal():
    print(generate_meeting_link("Test Company LLC"))

if __name__ == "__main__":
    test_cal()
