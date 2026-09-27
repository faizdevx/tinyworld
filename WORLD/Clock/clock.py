from dataclasses import dataclass

# dataclasses makes the work to make the classes way more easier by automating the constructor making for us !! 

@dataclass
class Clock:
    day:int=1
    hour:int=8

    # 1 day and my day usually starts at 8 am 
    
    def tick(self):
        self.hour+=1

        if self.hour>=24:
            self.hour=0
            self.day+=1

    # a regular day logic 


    @property

    def phase(self)->str:
        if 6<=self.hour<18:
            return "Day"
        return "Night"
    
    # day or night??? 

    def time_string(self)-> str:
        return f"Day{self.day}-{self.hour:02d}:00"

    #it should really look like real clock though !! 

    