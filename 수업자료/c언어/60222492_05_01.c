#include <stdio.h>
void main() {
	int hour, min, sec;

	printf("초를 입력하시오:");
	scanf("%d",&sec);
	
	hour = sec/ 3600;
	min = (sec%3600)/60;
	sec = (sec%3600)%60;
	printf("입력한 초는 %d시간 %d분%d초 입니다.",hour,min,sec);
}

