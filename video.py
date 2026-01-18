import yt_dlp

url= input("Enter the video URL: ")

ydl_opts = {


    'outtmpl': '%(title)s.%(ext)s'
  
  }
with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    ydl.download([url])

print("Download completed.")