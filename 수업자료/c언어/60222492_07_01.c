#include <stdio.h>
void main(){
	double x,y; 
	printf("x와 y좌표 값을 입력하시오:");
	scanf("%lf %lf",&x,&y);
	if(x>=0 && y>=0)
	printf("1사분면입니다.");
	else if(x<0 && y>=0)
	printf("2사분면입니다.");
	else if(x<0 && y<0)
	printf("3사분면입니다.");
	else
	printf("4사분면입니다.");
}
