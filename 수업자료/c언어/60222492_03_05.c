#include <stdio.h>
main(){
	int lcky;
	int nlcky;
	printf("당신의 행운의 숫자를 입력하시오:");
	scanf("%d", &lcky) ;
	printf("당신의 불행의 숫자를 입력하시오:");
	scanf("%d",&nlcky);
	printf("당신의 행운의 숫자는 %d이고, 불행의 숫자는 %d입니다.",lcky,nlcky);
}
