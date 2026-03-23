#include <stdio.h>
void main(){
	int num;
	printf("정수를 입력하시오:");
	scanf("%d",&num);
	if(num<0)
	num = num*(-1);
	printf("입력한 절댓값은 %d이다.",num);
}
